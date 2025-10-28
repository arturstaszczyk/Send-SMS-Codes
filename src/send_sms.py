#!/usr/bin/env python3
"""
SIM800C SMS Sender Script
Connects to SIM800C and sends SMS messages to specified phone number.
"""

import sys
import time

# Handle imports when running as script or module
try:
    from sim800c import SIM800C
except ImportError:
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from sim800c import SIM800C


class SMSSender(SIM800C):
    """Extended SIM800C driver for sending SMS messages."""
    
    def send_sms_message(self, phone_number, message):
        """
        Send an SMS message to a phone number.
        
        Args:
            phone_number: Recipient phone number (e.g., "+1234567890")
            message: SMS message content
            
        Returns:
            dict with 'success' and 'data' keys
        """
        print(f"\n=== Sending SMS to {phone_number} ===")
        
        # Make sure we're in text mode
        cmgf_result = self.send_at_command('AT+CMGF=1')
        if not cmgf_result['success']:
            print("✗ Failed to set SMS text mode")
            return {'success': False, 'data': ''}
        
        # Send AT+CMGS command
        cmgs_command = f'AT+CMGS="{phone_number}"'
        print(f"Sending: {cmgs_command}")
        
        # Clear input buffer
        self.ser.reset_input_buffer()
        
        # Send the command
        cmd = f"{cmgs_command}\r\n"
        self.ser.write(cmd.encode())
        
        # Wait for the "> " prompt from the module
        response_lines = []
        prompt_received = False
        start_time = time.time()
        timeout = 5  # 5 seconds timeout
        
        while (time.time() - start_time) < timeout:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                response_lines.append(line)
                print(f"Received: {line}")
                
                if '>' in line:
                    prompt_received = True
                    break
        
        if not prompt_received:
            print("✗ Did not receive '>' prompt from module")
            return {'success': False, 'data': ''}
        
        # Now send the message content followed by Ctrl+Z (0x1A)
        print(f"Sending message: {message}")
        self.ser.write(message.encode())
        self.ser.write(b'\x1A')  # Ctrl+Z to terminate and send
        
        # Wait for the response
        response_lines = []
        final_response_seen = False
        start_time = time.time()
        timeout = 10  # 10 seconds for sending
        
        while (time.time() - start_time) < timeout:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    response_lines.append(line)
                    print(f"Received: {line}")
                    
                    if 'OK' in line or 'ERROR' in line or '+CMGS:' in line:
                        final_response_seen = True
                        if 'OK' in line or '+CMGS:' in line:
                            # Give it a moment to potentially get more data
                            time.sleep(0.2)
                        break
            
            # Small sleep to avoid tight loop
            time.sleep(0.01)
        
        response_data = '\n'.join(response_lines)
        
        if 'OK' in response_data or '+CMGS:' in response_data:
            print(f"✓ SMS sent successfully")
            return {'success': True, 'data': response_data}
        else:
            print(f"✗ Failed to send SMS: {response_data}")
            return {'success': False, 'data': response_data}
    
    def send_sms(self, phone_number, messages):
        """
        Send multiple SMS messages to a phone number.
        
        Args:
            phone_number: Recipient phone number
            messages: List of message strings to send
            
        Returns:
            bool indicating overall success
        """
        try:
            print("\n=== Starting SMS Sending Process ===")
            
            # Send each message
            success_count = 0
            for i, message in enumerate(messages, 1):
                print(f"\n--- Sending Message {i} of {len(messages)} ---")
                result = self.send_sms_message(phone_number, message)
                
                if result['success']:
                    success_count += 1
                else:
                    print(f"✗ Failed to send message {i}")
                
                # Small delay between messages to avoid overwhelming the module
                if i < len(messages):
                    time.sleep(1)
            
            self.h1_message(f"✓ SMS Sending Complete! Sent {success_count} of {len(messages)} message(s)")
            
            return success_count == len(messages)
            
        except Exception as e:
            print(f"\n✗ Error during SMS sending: {e}")
            return False


def main():
    """Main entry point."""
    # Try to load environment variables from .env file
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Get phone number from environment
    phone_number = SIM800C.read_env_variable('SMS_PHONE_NUMBER')
    phone_number_log = SIM800C.read_env_variable('SMS_PHONE_NUMBER_LOG')
    
    # Get message number from command line argument (default to 1)
    message_number = 1
    if len(sys.argv) > 1:
        try:
            message_number = int(sys.argv[1])
        except ValueError:
            print(f"✗ Error: Invalid message number '{sys.argv[1]}'. Using default (1)")
            message_number = 1
    
    # Get the specified message from environment
    message_key = f'MESSAGE_{message_number}'
    message = SIM800C.read_env_variable(message_key)
    
    messages = [message]
    
    print(f"\nConfiguration:")
    print(f"  Phone Number: {phone_number}")
    print(f"  Phone Number: {phone_number_log}")
    print(f"  Number of messages: {len(messages)}")
    
    # Get port from environment variable or default
    port = SIM800C.read_env_variable('SIM800_PORT', '/dev/ttyS0')
    
    sender = SMSSender(port=port)
    
    # Connect
    if not sender.setup_connection():
        sender.h1_message("Failed to connect to SIM800C")
        sys.exit(1)
    
    statistics = {
        'primary_sent': 0,
        'primary_total': 0,
        'log_sent': 0,
        'log_total': 0
    }
    
    try:
        # Send SMS to primary recipient
        sender.h1_message(f"Sending to PRIMARY recipient: {phone_number}")
        primary_success = sender.send_sms(phone_number, messages)
        statistics['primary_sent'] = len(messages) if primary_success else 0
        statistics['primary_total'] = len(messages)
        
        # Create descriptive log message
        log_message = f"[LOG] Message sent to {phone_number}\nContent: {message}\nStatus: {'SUCCESS' if primary_success else 'FAILED'}"
        log_messages = [log_message]
        
        # Send log message to log recipient
        sender.h1_message(f"Sending to LOG recipient: {phone_number_log}")
        log_success = sender.send_sms(phone_number_log, log_messages)
        statistics['log_sent'] = len(log_messages) if log_success else 0
        statistics['log_total'] = len(log_messages)
        
    except Exception as e:
        print(f"\n✗ Error during operation: {e}")
    finally:
        sender.disconnect()
    
    # Display statistics
    print("\n" + "="*50)
    print("SMS SENDING STATISTICS")
    print("="*50)
    print(f"Primary recipient ({phone_number}):")
    print(f"  Sent: {statistics['primary_sent']}/{statistics['primary_total']}")
    print(f"Log recipient ({phone_number_log}):")
    print(f"  Sent: {statistics['log_sent']}/{statistics['log_total']}")
    print("="*50)
    
    overall_success = (statistics['primary_sent'] > 0 and statistics['log_sent'] > 0)
    sys.exit(0 if overall_success else 1)


if __name__ == '__main__':
    main()


