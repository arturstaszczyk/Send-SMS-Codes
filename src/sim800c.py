#!/usr/bin/env python3
"""
SIM800C Driver Module
Core serial communication and AT command handling for SIM800C modules.
"""

import serial
import time
import os
import sys

# Try to load environment variables from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is not installed, skip .env loading


class SIM800C:
    """Core driver for SIM800C GSM module."""
    
    def __init__(self, port='/dev/ttyS0', baudrate=115200, timeout=1):
        """Initialize serial connection to SIM800C module."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
    
    @staticmethod
    def read_env_variable(name, default=None):
        """
        Read an environment variable with error handling.
        
        Args:
            name: Environment variable name
            default: Default value if not set (optional)
        
        Returns:
            Environment variable value or default if set
        
        Exits:
            sys.exit(0) if variable is not set and no default provided
        """
        value = os.getenv(name)
        
        if value is None and default is None:
            print(f"✗ Error: {name} environment variable not set")
            print(f"Please set {name} in your .env file")
            sys.exit(0)
        
        return value if value is not None else default
        
    def connect(self):
        """Open serial connection."""


        self.h1_message("Connecting to SIM800C")

        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            print(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"Error opening serial port: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial connection closed")

    def h1_message(self, message):
        print("\n" + "="*50)
        print(message)
        print("="*50)

    def detect_baudrate(self):
        """Auto-detect the correct baudrate by testing common values."""
        common_baudrates = [115200, 9600, 19200, 38400, 57600]
        
        self.h1_message("Attempting to auto-detect baudrate...")
        for baudrate in common_baudrates:
            print(f"Trying {baudrate} baud...")
            
            try:
                self.baudrate = baudrate
                if self.ser and self.ser.is_open:
                    self.ser.close()
                
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=0.5,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE
                )
                
                # Try to send AT command
                test_result = self.send_at_command('AT', timeout=1)
                
                if test_result['success']:
                    print(f"✓ Detected baudrate: {baudrate}")
                    self.ser.timeout = self.timeout  # Reset to normal timeout
                    return True
                
                self.ser.close()
            except Exception as e:
                print(f"  Error at {baudrate}: {e}")
                if self.ser and self.ser.is_open:
                    self.ser.close()
                continue
        
        print("✗ Failed to detect baudrate")
        return False
    
    def send_at_command(self, command, wait_for_ok=True, timeout=2):
        """
        Send AT command and read response.
        
        Args:
            command: AT command string (e.g., 'ATI')
            wait_for_ok: Whether to wait for OK response
            timeout: Response timeout in seconds
        
        Returns:
            dict with 'success' and 'data' keys
        """
        self.h1_message(f"Sending AT command: {command}")
        if not self.ser or not self.ser.is_open:
            print("Serial port not open")
            return {'success': False, 'data': ''}
        
        # Flush any pending data
        self.ser.reset_input_buffer()
        
        # Send command
        cmd = f"{command}\r\n"
        self.ser.write(cmd.encode())
        print(f"Sending: {command}")
        
        # Read response
        start_time = time.time()
        response_lines = []
        final_response_seen = False
        last_data_time = time.time()
        
        # Wait a bit for initial response (some modules are slow)
        initial_wait = 0.3  # 300ms initial wait
        waited_initial = False
        
        while (time.time() - start_time) < timeout:
            if self.ser.in_waiting:
                waited_initial = True
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    response_lines.append(line)
                    print(f"Received: {line}")
                    last_data_time = time.time()
                    
                    # Check for final response indicators
                    if 'OK' in line or 'ERROR' in line:
                        final_response_seen = True
                        # Continue reading for a short period in case there's more data
            
            # If we saw OK/ERROR and no data has arrived for 50ms, stop
            if final_response_seen and (time.time() - last_data_time) > 0.05:
                break
            
            # Wait for initial response
            if not waited_initial and (time.time() - start_time) < initial_wait:
                time.sleep(0.05)
            else:
                # Small sleep to avoid tight loop
                time.sleep(0.01)
        
        # Filter out echo and control lines, keep actual data
        data_lines = [line for line in response_lines if line not in ['AT', 'OK', 'ERROR']]
        
        result = {
            'success': 'OK' in '\n'.join(response_lines),
            'data': '\n'.join(data_lines)
        }
        
        return result
    
    def parse_response_value(self, data, prefix):
        """
        Parse a response value like +CFUN: 1 or +CMGF: 1.
        
        Args:
            data: Response data string
            prefix: Prefix to look for (e.g., '+CFUN:')
        
        Returns:
            int value or None if not found
        """
        if prefix in data:
            try:
                value_str = data.split(prefix)[1].strip()
                return int(value_str.split()[0])
            except (ValueError, IndexError):
                return None
        return None
    
    def check_and_set_status(self, query_cmd, prefix, expected_value, set_cmd, 
                            status_name, success_msg=None, enable_msg=None):
        """
        Generic method to check status and set if needed.
        
        Args:
            query_cmd: Command to query status (e.g., 'AT+CFUN?')
            prefix: Response prefix to parse (e.g., '+CFUN:')
            expected_value: Expected value (e.g., 1)
            set_cmd: Command to set value (e.g., 'AT+CFUN=1')
            status_name: Name for logging
            success_msg: Custom success message
            enable_msg: Message when enabling
        
        Returns:
            bool indicating success
        """
        print(f"\n=== Checking {status_name} ===")
        result = self.send_at_command(query_cmd)
        
        if not result['success']:
            print(f"✗ Failed to check {status_name}")
            return False
        
        current_value = self.parse_response_value(result['data'], prefix)
        
        if current_value is None:
            print(f"Unexpected response format: {result['data']}")
            return False
        
        if current_value == expected_value:
            if success_msg:
                print(success_msg)
            else:
                print(f"✓ {status_name} is already correct ({prefix} {expected_value})")
            return True
        
        if enable_msg:
            print(enable_msg)
        else:
            print(f"{status_name} is {current_value}, setting to {expected_value}...")
        
        set_result = self.send_at_command(set_cmd)
        if set_result['success']:
            print(f"✓ {status_name} set successfully")
            if status_name == "Power":
                time.sleep(2)  # Give module time to restart
            return True
        else:
            print(f"✗ Failed to set {status_name}")
            return False
    
    def check_and_set_text_status(self, query_cmd, prefix, ready_value, 
                                  set_cmd_func, status_name, 
                                  success_msg=None, enable_msg=None):
        """
        Generic method to check text-based status and set if needed.
        Useful for statuses like PIN (READY vs SIM PIN) that return text values.
        
        Args:
            query_cmd: Command to query status (e.g., 'AT+CPIN?')
            prefix: Response prefix to parse (e.g., '+CPIN:')
            ready_value: Value indicating ready state (e.g., 'READY')
            set_cmd_func: Function that returns the command to set value (e.g., lambda: f'AT+CPIN={pin}')
            status_name: Name for logging
            success_msg: Custom success message
            enable_msg: Message when enabling
        
        Returns:
            bool indicating success
        """
        print(f"\n=== Checking {status_name} ===")
        result = self.send_at_command(query_cmd)
        
        if not result['success']:
            print(f"✗ Failed to check {status_name}")
            return False
        
        # Check if the ready_value is in the data
        if ready_value in result['data']:
            if success_msg:
                print(success_msg)
            else:
                print(f"✓ {status_name} is ready")
            return True
        
        # Not ready - need to set it
        if enable_msg:
            print(enable_msg)
        else:
            print(f"{status_name} not ready, setting...")
        
        # Get the set command from the provided function
        set_cmd = set_cmd_func()
        if set_cmd is None:
            print(f"✗ Failed to generate set command for {status_name}")
            return False
        
        set_result = self.send_at_command(set_cmd)
        if set_result['success']:
            print(f"✓ {status_name} set successfully")
            if status_name == "PIN":
                time.sleep(1)
            return True
        else:
            print(f"✗ Failed to set {status_name}")
            return False
    
    def verify_module(self):
        """Verify we're talking to SIM800 module using ATI command."""
        print("\n=== Verifying SIM800 Module ===")
        result = self.send_at_command('ATI')
        
        if result['success']:
            if 'SIM800' in result['data']:
                print("✓ Module verified: SIM800")
                print(f"Response: {result['data']}")
                return True
            else:
                print(f"⚠ Warning: Unexpected module response: {result['data']}")
                return True  # Still proceed if we get OK
        else:
            print("✗ Failed to verify module")
            return False
    
    def setup_connection(self):
        """
        Setup and initialize connection to SIM800 module.
        
        Returns:
            bool indicating success
        """
        # Try to connect (use super() to avoid naming conflicts)
        if not self.ser or not self.ser.is_open:
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE
                )
                print(f"Connected to {self.port} at {self.baudrate} baud")
            except serial.SerialException as e:
                print(f"Error opening serial port: {e}")
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
            
            return True
            
        except Exception as e:
            print(f"\n✗ Error during connection setup: {e}")
            return False

