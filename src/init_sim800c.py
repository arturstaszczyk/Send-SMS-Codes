#!/usr/bin/env python3
"""
SIM800C Initialization Script
Connects to SIM800C via serial port and performs initial setup and verification.
"""

import serial
import time
import os
import sys

# Handle imports when running as script or module
try:
    from sim800c import SIM800C as BaseSIM800C
except ImportError:
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from sim800c import SIM800C as BaseSIM800C

# Try to load environment variables from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is not installed, skip .env loading


class SIM800CInitializer(BaseSIM800C):
    def __init__(self, port='/dev/ttyS0', baudrate=115200, timeout=1):
        """Initialize SIM800C initializer."""
        super().__init__(port, baudrate, timeout)
    
    def check_and_enable_power(self):
        """Check power status with AT+CFUN? and enable if necessary."""
        return self.check_and_set_status(
            query_cmd='AT+CFUN?',
            prefix='+CFUN:',
            expected_value=1,
            set_cmd='AT+CFUN=1',
            status_name='Power',
            success_msg='✓ Device is powered on (CFUN=1)',
            enable_msg='Device is powered off, enabling power...'
        )
    
    def check_and_set_pin(self):
        """Check PIN status and set if needed from environment variable."""
        def get_pin_cmd():
            """Generate PIN command from environment variable."""
            # Try to read PIN, but it's optional
            value = os.getenv('SIM800_PIN')
            if value:
                return f'AT+CPIN={value}'
            else:
                print("✗ PIN required but SIM800_PIN environment variable not set")
                return None
        
        return self.check_and_set_text_status(
            query_cmd='AT+CPIN?',
            prefix='+CPIN:',
            ready_value='READY',
            set_cmd_func=get_pin_cmd,
            status_name='PIN',
            success_msg='✓ PIN is ready - no PIN required',
            enable_msg='PIN required'
        )
    
    def check_and_set_sms_mode(self):
        """Verify SMS text mode and set to 1 if necessary."""
        return self.check_and_set_status(
            query_cmd='AT+CMGF?',
            prefix='+CMGF:',
            expected_value=1,
            set_cmd='AT+CMGF=1',
            status_name='SMS Mode',
            success_msg='✓ SMS text mode is already set (CMGF=1)'
        )
    
    def initialize(self):
        """Perform complete initialization sequence."""
        print("\n" + "="*50)
        print("SIM800C Initialization Sequence")
        print("="*50)
        
        # Try to connect and detect baudrate if needed
        initial_success = self.connect()
        if not initial_success:
            return False
        
        try:
            # Wait a bit for module to be ready
            time.sleep(1)
            
            # Step 0: Try to disable echo and detect baudrate if needed
            print("\n=== Disabling Echo ===")
            echo_result = self.send_at_command('ATE0')
            
            # If echo command failed, try to auto-detect baudrate
            if not echo_result['success'] and echo_result['data'] == '':
                print("\nNo response from module, attempting baudrate detection...")
                if not self.detect_baudrate():
                    print("✗ Failed to detect baudrate and module not responding")
                    return False
                # Retry echo after baudrate detection
                echo_result = self.send_at_command('ATE0')
            
            # Step 1: Verify module
            if not self.verify_module():
                print("\n✗ Initialization failed: Module verification failed")
                return False
            
            # Step 2: Check and enable power
            if not self.check_and_enable_power():
                print("\n✗ Initialization failed: Power management failed")
                return False
            
            # Step 3: Check and set PIN
            if not self.check_and_set_pin():
                print("\n✗ Initialization failed: PIN management failed")
                return False
            
            # Step 4: Check and set SMS mode
            if not self.check_and_set_sms_mode():
                print("\n✗ Initialization failed: SMS mode setup failed")
                return False
            
            print("\n" + "="*50)
            print("✓ SIM800C Initialization Complete!")
            print("="*50)
            return True
            
        except Exception as e:
            print(f"\n✗ Error during initialization: {e}")
            return False
        finally:
            self.disconnect()


def main():
    """Main entry point."""
    # Check for serial port argument
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyS0'
    
    sim800 = SIM800CInitializer(port=port)
    success = sim800.initialize()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

