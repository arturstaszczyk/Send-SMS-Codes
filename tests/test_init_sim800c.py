#!/usr/bin/env python3
"""
Unit tests for SIM800C initialization script.
"""

import pytest
import serial
import time
from unittest.mock import Mock, patch, MagicMock, call
from io import BytesIO
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import the module to test
from src.init_sim800c import SIM800CInitializer


class TestSIM800CInitializer:
    """Test suite for SIM800C class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.sim800 = SIM800CInitializer(port='/dev/ttyS0', baudrate=115200, timeout=1)
    
    def test_init(self):
        """Test SIM800CInitializer initialization."""
        assert self.sim800.port == '/dev/ttyS0'
        assert self.sim800.baudrate == 115200
        assert self.sim800.timeout == 1
        assert self.sim800.ser is None
    
    @patch('serial.Serial')
    def test_connect_success(self, mock_serial):
        """Test successful connection."""
        mock_ser = Mock()
        mock_serial.return_value = mock_ser
        
        result = self.sim800.connect()
        
        assert result is True
        assert self.sim800.ser == mock_ser
        mock_serial.assert_called_once_with(
            port='/dev/ttyS0',
            baudrate=115200,
            timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE
        )
    
    @patch('serial.Serial')
    def test_connect_failure(self, mock_serial):
        """Test connection failure."""
        mock_serial.side_effect = serial.SerialException("Port not available")
        
        result = self.sim800.connect()
        
        assert result is False
    
    @patch('serial.Serial')
    def test_disconnect(self, mock_serial):
        """Test disconnection."""
        mock_ser = Mock()
        mock_ser.is_open = True
        self.sim800.ser = mock_ser
        
        self.sim800.disconnect()
        
        mock_ser.close.assert_called_once()
    
    def test_disconnect_not_connected(self):
        """Test disconnection when not connected."""
        self.sim800.ser = None
        # Should not raise an error
        self.sim800.disconnect()
    
    @patch('serial.Serial')
    def test_send_at_command_success(self, mock_serial):
        """Test sending AT command with success response."""
        mock_ser = Mock()
        mock_ser.is_open = True
        # in_waiting will return False after responses are exhausted
        in_waiting_count = 0
        def in_waiting_side_effect():
            nonlocal in_waiting_count
            in_waiting_count += 1
            return in_waiting_count <= 4  # Stop after a few checks
        mock_ser.in_waiting = Mock(side_effect=in_waiting_side_effect)
        
        # Simulate response lines
        responses = iter([
            BytesIO(b'AT\r\n').readline(),  # Echo of command
            BytesIO(b'SIM800 R14.18\r\n').readline(),  # Response
            BytesIO(b'OK\r\n').readline(),  # OK
        ])
        def readline_side_effect():
            try:
                return next(responses)
            except StopIteration:
                return b'\r\n'
        mock_ser.readline.side_effect = readline_side_effect
        mock_serial.return_value = mock_ser
        self.sim800.ser = mock_ser
        
        result = self.sim800.send_at_command('ATI')
        
        assert result['success'] is True
        assert 'SIM800 R14.18' in result['data']
        mock_ser.write.assert_called_once()
    
    @patch('serial.Serial')
    def test_send_at_command_error(self, mock_serial):
        """Test sending AT command with error response."""
        mock_ser = Mock()
        mock_ser.is_open = True
        # in_waiting will return False after responses are exhausted
        in_waiting_count = 0
        def in_waiting_side_effect():
            nonlocal in_waiting_count
            in_waiting_count += 1
            return in_waiting_count <= 3  # Stop after a few checks
        mock_ser.in_waiting = Mock(side_effect=in_waiting_side_effect)
        
        responses = iter([
            BytesIO(b'AT\r\n').readline(),
            BytesIO(b'ERROR\r\n').readline(),
        ])
        def readline_side_effect():
            try:
                return next(responses)
            except StopIteration:
                return b'\r\n'
        mock_ser.readline.side_effect = readline_side_effect
        mock_serial.return_value = mock_ser
        self.sim800.ser = mock_ser
        
        result = self.sim800.send_at_command('AT+TEST')
        
        assert result['success'] is False
        assert result['data'] == ''  # ERROR and AT echo are both filtered out
    
    @patch('serial.Serial')
    def test_send_at_command_not_connected(self, mock_serial):
        """Test sending command when not connected."""
        result = self.sim800.send_at_command('AT')
        
        assert result['success'] is False
        assert result['data'] == ''
    
    def test_verify_module_success(self):
        """Test module verification with correct response."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'command': 'ATI',
                'response': 'SIM800 R14.18\nOK',
                'success': True,
                'data': 'SIM800 R14.18'
            }
            
            result = self.sim800.verify_module()
            
            assert result is True
            mock_send.assert_called_once_with('ATI')
    
    def test_verify_module_failure(self):
        """Test module verification with failure."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'command': 'ATI',
                'response': 'ERROR',
                'success': False,
                'data': ''
            }
            
            result = self.sim800.verify_module()
            
            assert result is False
    
    def test_check_and_enable_power_already_on(self):
        """Test power check when already powered on."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'command': 'AT+CFUN?',
                'response': '+CFUN: 1\nOK',
                'success': True,
                'data': '+CFUN: 1'
            }
            
            result = self.sim800.check_and_enable_power()
            
            assert result is True
            mock_send.assert_called_once_with('AT+CFUN?')
    
    def test_check_and_enable_power_turn_on(self):
        """Test power enable when device is off."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {
                    'command': 'AT+CFUN?',
                    'response': '+CFUN: 0\nOK',
                    'success': True,
                    'data': '+CFUN: 0'
                },
                {
                    'command': 'AT+CFUN=1',
                    'response': 'OK',
                    'success': True,
                    'data': ''
                }
            ]
            with patch('time.sleep'):
                result = self.sim800.check_and_enable_power()
                
                assert result is True
                assert mock_send.call_count == 2
    
    def test_check_and_enable_power_enable_fails(self):
        """Test power enable failure."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {
                    'command': 'AT+CFUN?',
                    'response': '+CFUN: 0\nOK',
                    'success': True,
                    'data': '+CFUN: 0'
                },
                {
                    'command': 'AT+CFUN=1',
                    'response': 'ERROR',
                    'success': False,
                    'data': ''
                }
            ]
            with patch('time.sleep'):
                result = self.sim800.check_and_enable_power()
                
                assert result is False
    
    def test_check_and_set_pin_ready(self):
        """Test PIN check when ready."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'command': 'AT+CPIN?',
                'response': '+CPIN: READY\nOK',
                'success': True,
                'data': '+CPIN: READY'
            }
            
            result = self.sim800.check_and_set_pin()
            
            assert result is True
            mock_send.assert_called_once_with('AT+CPIN?')
    
    @patch.dict(os.environ, {'SIM800_PIN': '1234'})
    def test_check_and_set_pin_set_from_env(self):
        """Test PIN setting from environment variable."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {
                    'command': 'AT+CPIN?',
                    'response': '+CPIN: SIM PIN\nOK',
                    'success': True,
                    'data': '+CPIN: SIM PIN'
                },
                {
                    'command': 'AT+CPIN=1234',
                    'response': 'OK',
                    'success': True,
                    'data': ''
                }
            ]
            with patch('time.sleep'):
                result = self.sim800.check_and_set_pin()
                
                assert result is True
                assert mock_send.call_count == 2
                mock_send.assert_any_call('AT+CPIN=1234')
    
    @patch.dict(os.environ, {}, clear=True)
    def test_check_and_set_pin_no_env_var(self):
        """Test PIN requirement without environment variable."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'command': 'AT+CPIN?',
                'response': '+CPIN: SIM PIN\nOK',
                'success': True,
                'data': '+CPIN: SIM PIN'
            }
            
            result = self.sim800.check_and_set_pin()
            
            assert result is False
            mock_send.assert_called_once_with('AT+CPIN?')
    
    def test_check_and_set_sms_mode_already_set(self):
        """Test SMS mode check when already set to text mode."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'command': 'AT+CMGF?',
                'success': True,
                'data': '+CMGF: 1\n\nOK'
            }
            
            result = self.sim800.check_and_set_sms_mode()
            
            assert result is True
            mock_send.assert_called_once_with('AT+CMGF?')
    
    def test_check_and_set_sms_mode_set_to_one(self):
        """Test SMS mode setting to text mode."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {
                    'command': 'AT+CMGF?',
                    'response': '+CMGF: 0\nOK',
                    'success': True,
                    'data': '+CMGF: 0'
                },
                {
                    'command': 'AT+CMGF=1',
                    'response': 'OK',
                    'success': True,
                    'data': ''
                }
            ]
            
            result = self.sim800.check_and_set_sms_mode()
            
            assert result is True
            assert mock_send.call_count == 2
            mock_send.assert_any_call('AT+CMGF=1')
    
    def test_initialize_full_success(self):
        """Test complete initialization sequence with success."""
        with patch.object(self.sim800, 'connect') as mock_connect, \
             patch.object(self.sim800, 'disconnect') as mock_disconnect, \
             patch.object(self.sim800, 'verify_module') as mock_verify, \
             patch.object(self.sim800, 'check_and_enable_power') as mock_power, \
             patch.object(self.sim800, 'check_and_set_pin') as mock_pin, \
             patch.object(self.sim800, 'check_and_set_sms_mode') as mock_sms, \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            mock_verify.return_value = True
            mock_power.return_value = True
            mock_pin.return_value = True
            mock_sms.return_value = True
            
            result = self.sim800.initialize()
            
            assert result is True
            mock_connect.assert_called_once()
            mock_disconnect.assert_called_once()
            mock_verify.assert_called_once()
            mock_power.assert_called_once()
            mock_pin.assert_called_once()
            mock_sms.assert_called_once()
    
    def test_initialize_connection_failure(self):
        """Test initialization when connection fails."""
        with patch.object(self.sim800, 'connect') as mock_connect, \
             patch.object(self.sim800, 'disconnect'):
            
            mock_connect.return_value = False
            
            result = self.sim800.initialize()
            
            assert result is False
    
    def test_initialize_verification_failure(self):
        """Test initialization when verification fails."""
        with patch.object(self.sim800, 'connect') as mock_connect, \
             patch.object(self.sim800, 'disconnect') as mock_disconnect, \
             patch.object(self.sim800, 'verify_module') as mock_verify, \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            mock_verify.return_value = False
            
            result = self.sim800.initialize()
            
            assert result is False
            mock_disconnect.assert_called_once()
    
    def test_initialize_power_failure(self):
        """Test initialization when power check fails."""
        with patch.object(self.sim800, 'connect') as mock_connect, \
             patch.object(self.sim800, 'disconnect') as mock_disconnect, \
             patch.object(self.sim800, 'verify_module') as mock_verify, \
             patch.object(self.sim800, 'check_and_enable_power') as mock_power, \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            mock_verify.return_value = True
            mock_power.return_value = False
            
            result = self.sim800.initialize()
            
            assert result is False
    
    def test_initialize_pin_failure(self):
        """Test initialization when PIN check fails."""
        with patch.object(self.sim800, 'connect') as mock_connect, \
             patch.object(self.sim800, 'disconnect') as mock_disconnect, \
             patch.object(self.sim800, 'verify_module') as mock_verify, \
             patch.object(self.sim800, 'check_and_enable_power') as mock_power, \
             patch.object(self.sim800, 'check_and_set_pin') as mock_pin, \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            mock_verify.return_value = True
            mock_power.return_value = True
            mock_pin.return_value = False
            
            result = self.sim800.initialize()
            
            assert result is False
    
    def test_initialize_sms_failure(self):
        """Test initialization when SMS mode check fails."""
        with patch.object(self.sim800, 'connect') as mock_connect, \
             patch.object(self.sim800, 'disconnect') as mock_disconnect, \
             patch.object(self.sim800, 'verify_module') as mock_verify, \
             patch.object(self.sim800, 'check_and_enable_power') as mock_power, \
             patch.object(self.sim800, 'check_and_set_pin') as mock_pin, \
             patch.object(self.sim800, 'check_and_set_sms_mode') as mock_sms, \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            mock_verify.return_value = True
            mock_power.return_value = True
            mock_pin.return_value = True
            mock_sms.return_value = False
            
            result = self.sim800.initialize()
            
            assert result is False
    
    def test_parse_response_value(self):
        """Test parsing response value."""
        # Test successful parse
        data = '+CFUN: 1'
        value = self.sim800.parse_response_value(data, '+CFUN:')
        assert value == 1
        
        # Test parse with extra data
        data = '+CMGF: 1\nOK'
        value = self.sim800.parse_response_value(data, '+CMGF:')
        assert value == 1
        
        # Test parse not found
        data = 'OK'
        value = self.sim800.parse_response_value(data, '+CMGF:')
        assert value is None
        
        # Test parse with invalid number
        data = '+CFUN: abc'
        value = self.sim800.parse_response_value(data, '+CFUN:')
        assert value is None
    
    @patch('serial.Serial')
    def test_detect_baudrate_success(self, mock_serial):
        """Test successful baudrate detection."""
        mock_ser = Mock()
        mock_ser.is_open = True
        # in_waiting will return False after responses are exhausted
        in_waiting_count = 0
        def in_waiting_side_effect():
            nonlocal in_waiting_count
            in_waiting_count += 1
            return in_waiting_count <= 4
        mock_ser.in_waiting = Mock(side_effect=in_waiting_side_effect)
        
        # Mock readline to return OK response
        responses = iter([
            BytesIO(b'OK\r\n').readline(),
        ])
        def readline_side_effect():
            try:
                return next(responses)
            except StopIteration:
                return b'\r\n'
        mock_ser.readline.side_effect = readline_side_effect
        mock_serial.return_value = mock_ser
        self.sim800.ser = mock_ser
        
        result = self.sim800.detect_baudrate()
        
        assert result is True
    
    @patch('serial.Serial')
    def test_detect_baudrate_failure(self, mock_serial):
        """Test baudrate detection failure."""
        mock_ser = Mock()
        mock_ser.is_open = True
        in_waiting_count = 0
        def in_waiting_side_effect():
            nonlocal in_waiting_count
            in_waiting_count += 1
            return False
        mock_ser.in_waiting = Mock(side_effect=in_waiting_side_effect)
        
        def readline_side_effect():
            return b'\r\n'
        mock_ser.readline.side_effect = readline_side_effect
        mock_serial.return_value = mock_ser
        self.sim800.ser = mock_ser
        
        result = self.sim800.detect_baudrate()
        
        assert result is False
    
    def test_check_and_set_text_status_ready(self):
        """Test text status check when ready."""
        def dummy_cmd_func():
            return 'AT+TEST=value'
        
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'success': True,
                'data': '+TEST: READY'
            }
            
            result = self.sim800.check_and_set_text_status(
                query_cmd='AT+TEST?',
                prefix='+TEST:',
                ready_value='READY',
                set_cmd_func=dummy_cmd_func,
                status_name='Test Status',
                success_msg='✓ Test ready'
            )
            
            assert result is True
            mock_send.assert_called_once_with('AT+TEST?')
    
    @patch.dict(os.environ, {'TEST_VALUE': '12345'})
    def test_check_and_set_text_status_needs_setting(self):
        """Test text status check when needs setting."""
        def get_test_cmd():
            val = os.getenv('TEST_VALUE')
            return f'AT+TEST={val}'
        
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {
                    'success': True,
                    'data': '+TEST: NEEDS_SETTING'
                },
                {
                    'success': True,
                    'data': ''
                }
            ]
            
            with patch('time.sleep'):
                result = self.sim800.check_and_set_text_status(
                    query_cmd='AT+TEST?',
                    prefix='+TEST:',
                    ready_value='GOOD',
                    set_cmd_func=get_test_cmd,
                    status_name='Test Status',
                    enable_msg='Setting test...'
                )
                
                assert result is True
                assert mock_send.call_count == 2
                mock_send.assert_any_call('AT+TEST=12345')
    
    def test_check_and_set_text_status_no_cmd(self):
        """Test text status when set command function returns None."""
        def get_test_cmd():
            return None
        
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'success': True,
                'data': '+TEST: BAD_STATE'
            }
            
            result = self.sim800.check_and_set_text_status(
                query_cmd='AT+TEST?',
                prefix='+TEST:',
                ready_value='GOOD',
                set_cmd_func=get_test_cmd,
                status_name='Test Status'
            )
            
            assert result is False
            mock_send.assert_called_once_with('AT+TEST?')
    
    def test_check_and_set_text_status_set_fails(self):
        """Test text status when setting fails."""
        def get_test_cmd():
            return 'AT+TEST=value'
        
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {
                    'success': True,
                    'data': '+TEST: BAD_STATE'
                },
                {
                    'success': False,
                    'data': ''
                }
            ]
            
            result = self.sim800.check_and_set_text_status(
                query_cmd='AT+TEST?',
                prefix='+TEST:',
                ready_value='GOOD',
                set_cmd_func=get_test_cmd,
                status_name='Test Status'
            )
            
            assert result is False
            assert mock_send.call_count == 2
    
    def test_check_and_set_text_status_query_fails(self):
        """Test text status when query fails."""
        def get_test_cmd():
            return 'AT+TEST=value'
        
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'success': False,
                'data': ''
            }
            
            result = self.sim800.check_and_set_text_status(
                query_cmd='AT+TEST?',
                prefix='+TEST:',
                ready_value='READY',
                set_cmd_func=get_test_cmd,
                status_name='Test Status'
            )
            
            assert result is False
            mock_send.assert_called_once_with('AT+TEST?')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

