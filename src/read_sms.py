#!/usr/bin/env python3
"""
SIM800C SMS Reader Script
Connects to SIM800C and lists all SMS messages using AT+CMGL="ALL" command.
"""

import sys
import time
from .sim800c import SIM800C


class SMSReader(SIM800C):
    """Extended SIM800C driver for reading SMS messages."""
    
    def list_all_sms(self):
        """
        List all SMS messages using AT+CMGL="ALL" command.
        
        Returns:
            list of dictionaries with SMS data or None on failure
        """
        print("\n=== Reading SMS Messages ===")
        
        # Make sure we're in text mode
        cmgf_result = self.send_at_command('AT+CMGF=1')
        if not cmgf_result['success']:
            print("✗ Failed to set SMS text mode")
            return None
        
        # Read all SMS messages
        result = self.send_at_command('AT+CMGL="ALL"', timeout=5)
        
        if not result['success']:
            print("✗ Failed to read SMS messages")
            return None
        
        if not result['data']:
            print("✓ No SMS messages found")
            return []
        
        # Parse SMS messages
        messages = self.parse_sms_messages(result['data'])
        
        print(f"✓ Found {len(messages)} SMS message(s)")
        return messages
    
    def parse_sms_messages(self, data):
        """
        Parse SMS message data from AT+CMGL response.
        
        Format: +CMGL: index,status,number,timestamp,data
        Example: +CMGL: 0,"REC UNREAD","+1234567890","23/06/15,10:20:30+00"
        
        Args:
            data: Response data string
            
        Returns:
            list of dictionaries with parsed SMS data
        """
        messages = []
        lines = data.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('+CMGL:'):
                try:
                    # Parse the header line
                    # Format: +CMGL: index,status,"sender","timestamp"
                    # Note: timestamp may contain commas, so we need special handling
                    
                    # Remove the +CMGL: prefix to get the actual data
                    header = line[len('+CMGL:'):].strip()
                    
                    # Parse with respect to quoted strings
                    parts = []
                    current_part = ''
                    in_quotes = False
                    
                    for char in header:
                        if char == '"':
                            in_quotes = not in_quotes
                            current_part += char
                        elif char == ',' and not in_quotes:
                            if current_part:
                                parts.append(current_part.strip())
                            current_part = ''
                        else:
                            current_part += char
                    
                    # Don't forget the last part
                    if current_part:
                        parts.append(current_part.strip())
                    
                    if len(parts) >= 4:
                        index = parts[0].strip()
                        
                        # Parse status - handle quoted and unquoted
                        status_raw = parts[1].strip()
                        status = status_raw.strip('"')
                        
                        # Parse sender number - remove quotes
                        sender_raw = parts[2].strip()
                        sender = sender_raw.strip('"')
                        
                        # Parse timestamp - remove quotes
                        timestamp_raw = parts[3].strip()
                        timestamp = timestamp_raw.strip('"')
                        
                        # Get the actual message content (next line)
                        message_content = ''
                        if i + 1 < len(lines):
                            message_content = lines[i + 1].strip()
                        
                        messages.append({
                            'index': index,
                            'status': status,
                            'sender': sender,
                            'timestamp': timestamp,
                            'content': message_content
                        })
                        
                        print(f"\nMessage {index}:")
                        print(f"  Status: {status}")
                        print(f"  From: {sender}")
                        print(f"  Time: {timestamp}")
                        # Try to decode message content if it appears to be hex-encoded Unicode
                        try:
                            # Check if content looks like hex-encoded (even length, all hex chars)
                            if message_content and len(message_content) % 2 == 0 and all(c in '0123456789ABCDEFabcdef' for c in message_content):
                                # Try to decode as UCS2/UTF-16BE (common for GSM Unicode SMS)
                                decoded_content = bytes.fromhex(message_content).decode('utf-16-be')
                                print(f"  Content: {decoded_content}")
                            else:
                                print(f"  Content: {message_content}")
                        except (ValueError, UnicodeDecodeError):
                            # If decoding fails, print as-is
                            print(f"  Content: {message_content}")
                    
                        i += 2  # Skip the message content line
                    else:
                        i += 1
                except Exception as e:
                    print(f"Error parsing SMS line: {line}")
                    print(f"Error: {e}")
                    i += 1
            else:
                i += 1
        
        return messages
    
    def delete_sms(self, index):
        """
        Delete an SMS message by index.
        
        Args:
            index: SMS index to delete
            
        Returns:
            bool indicating success
        """
        result = self.send_at_command(f'AT+CMGD={index}')
        
        if result['success']:
            print(f"✓ SMS {index} deleted")
            return True
        else:
            print(f"✗ Failed to delete SMS {index}")
            return False
    
    def read_and_connect(self):
        """
        Connect to module and read SMS messages.
        
        Returns:
            bool indicating success
        """
        print("\n" + "="*50)
        print("SIM800C SMS Reader")
        print("="*50)
        
        # Try to connect
        initial_success = self.connect()
        if not initial_success:
            return False
        
        try:
            # Wait a bit for module to be ready
            time.sleep(1)
            
            # Disable echo
            print("\n=== Disabling Echo ===")
            echo_result = self.send_at_command('ATE0')
            
            # If echo command failed, try to auto-detect baudrate
            if not echo_result['success'] and echo_result['data'] == '':
                print("\nNo response from module, attempting baudrate detection...")
                if not self.detect_baudrate():
                    print("✗ Failed to detect baudrate and module not responding")
                    return False
                # Retry echo after baudrate detection
                self.send_at_command('ATE0')
            
            # Read SMS messages
            messages = self.list_all_sms()
            
            if messages is None:
                print("\n✗ Failed to read SMS messages")
                return False
            
            print("\n" + "="*50)
            print(f"✓ SMS Reading Complete! Found {len(messages) if messages else 0} message(s)")
            print("="*50)
            
            return True
            
        except Exception as e:
            print(f"\n✗ Error during SMS reading: {e}")
            return False
        finally:
            self.disconnect()


def main():
    """Main entry point."""
    # Check for serial port argument
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyS0'
    
    reader = SMSReader(port=port)
    success = reader.read_and_connect()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

