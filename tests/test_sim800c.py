#!/usr/bin/env python3
"""
Unit tests for SIM800C base driver module.
"""

import pytest
import serial
import time
from unittest.mock import Mock, patch
from io import BytesIO
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.sim800c import SIM800C


class TestSIM800C:
    """Test suite for SIM800C base class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.sim800 = SIM800C(port='/dev/ttyS0', baudrate=115200, timeout=1)
    
    def test_init(self):
        """Test SIM800C initialization."""
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
        mock_serial.assert_called_once()
    
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
        in_waiting_count = 0
        
        def in_waiting_side_effect():
            nonlocal in_waiting_count
            in_waiting_count += 1
            return in_waiting_count <= 4
        
        mock_ser.in_waiting = Mock(side_effect=in_waiting_side_effect)
        mock_ser.reset_input_buffer = Mock()
        
        responses = iter([
            BytesIO(b'AT\r\n').readline(),
            BytesIO(b'SIM800 R14.18\r\n').readline(),
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
        
        result = self.sim800.send_at_command('ATI')
        
        assert result['success'] is True
        assert 'SIM800 R14.18' in result['data']
    
    @patch('serial.Serial')
    def test_send_at_command_not_connected(self, mock_serial):
        """Test sending command when not connected."""
        result = self.sim800.send_at_command('AT')
        
        assert result['success'] is False
        assert result['data'] == ''
    
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
    
    def test_check_and_set_status_already_correct(self):
        """Test check_and_set_status when already correct."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'success': True,
                'data': '+CFUN: 1'
            }
            
            result = self.sim800.check_and_set_status(
                query_cmd='AT+CFUN?',
                prefix='+CFUN:',
                expected_value=1,
                set_cmd='AT+CFUN=1',
                status_name='Test'
            )
            
            assert result is True
            mock_send.assert_called_once_with('AT+CFUN?')
    
    def test_check_and_set_status_needs_setting(self):
        """Test check_and_set_status when needs setting."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {'success': True, 'data': '+CFUN: 0'},
                {'success': True, 'data': ''}
            ]
            
            result = self.sim800.check_and_set_status(
                query_cmd='AT+CFUN?',
                prefix='+CFUN:',
                expected_value=1,
                set_cmd='AT+CFUN=1',
                status_name='Test'
            )
            
            assert result is True
            assert mock_send.call_count == 2
    
    def test_check_and_set_status_set_fails(self):
        """Test check_and_set_status when setting fails."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {'success': True, 'data': '+CFUN: 0'},
                {'success': False, 'data': ''}
            ]
            
            result = self.sim800.check_and_set_status(
                query_cmd='AT+CFUN?',
                prefix='+CFUN:',
                expected_value=1,
                set_cmd='AT+CFUN=1',
                status_name='Test'
            )
            
            assert result is False
    
    def test_check_and_set_text_status_ready(self):
        """Test check_and_set_text_status when ready."""
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
                status_name='Test Status'
            )
            
            assert result is True
    
    def test_check_and_set_text_status_needs_setting(self):
        """Test check_and_set_text_status when needs setting."""
        def get_test_cmd():
            return 'AT+TEST=12345'
        
        with patch.object(self.sim800, 'send_at_command') as mock_send, \
             patch('time.sleep'):
            mock_send.side_effect = [
                {'success': True, 'data': '+TEST: NEEDS_SETTING'},
                {'success': True, 'data': ''}
            ]
            
            result = self.sim800.check_and_set_text_status(
                query_cmd='AT+TEST?',
                prefix='+TEST:',
                ready_value='READY',
                set_cmd_func=get_test_cmd,
                status_name='Test Status'
            )
            
            assert result is True
    
    def test_verify_module_success(self):
        """Test module verification with correct response."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'success': True,
                'data': 'SIM800 R14.18'
            }
            
            result = self.sim800.verify_module()
            
            assert result is True
    
    def test_verify_module_failure(self):
        """Test module verification with failure."""
        with patch.object(self.sim800, 'send_at_command') as mock_send:
            mock_send.return_value = {
                'success': False,
                'data': ''
            }
            
            result = self.sim800.verify_module()
            
            assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

