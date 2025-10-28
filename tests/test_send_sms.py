#!/usr/bin/env python3
"""
Unit tests for SMS sending functionality.
"""

import pytest
import serial
import time
import os
from unittest.mock import Mock, patch, mock_open
from io import BytesIO

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.send_sms import SMSSender


class TestSMSSender:
    """Test suite for SMSSender class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.sender = SMSSender(port='/dev/ttyS0', baudrate=115200, timeout=1)
    
    def test_init(self):
        """Test SMSSender initialization."""
        assert self.sender.port == '/dev/ttyS0'
        assert self.sender.baudrate == 115200
        assert self.sender.timeout == 1
    
    def test_send_sms_message_success(self):
        """Test successfully sending an SMS message."""
        mock_ser = Mock()
        mock_ser.is_open = True
        mock_ser.reset_input_buffer = Mock()
        
        # Simulate the flow:
        # 1. CMGF=1 response
        # 2. CMGS command
        # 3. Prompt response "> "
        # 4. After sending Ctrl+Z, OK response
        call_count = 0
        
        def in_waiting_side_effect():
            nonlocal call_count
            call_count += 1
            # Return True for initial check, then False when done
            return call_count <= 10
        
        mock_ser.in_waiting = Mock(side_effect=in_waiting_side_effect)
        
        readline_responses = [
            b'\r\n',  # Empty line
            b'> \r\n',  # Prompt
            b'\r\n',  # Empty after sending
            b'+CMGS: 1\r\n',  # Success response
            b'OK\r\n'  # Final OK
        ]
        readline_iterator = iter(readline_responses)
        
        def readline_side_effect():
            try:
                return next(readline_iterator)
            except StopIteration:
                return b'\r\n'
        
        mock_ser.readline.side_effect = readline_side_effect
        
        self.sender.ser = mock_ser
        
        with patch.object(self.sender, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': True, 'data': ''}
            
            result = self.sender.send_sms_message('+1234567890', 'Test message')
            
            assert result['success'] is True
            mock_send.assert_called_once_with('AT+CMGF=1')
            # Verify that write was called for the message and Ctrl+Z
            assert mock_ser.write.call_count >= 2
    
    def test_send_sms_message_cmgf_fails(self):
        """Test sending SMS when CMGF fails."""
        mock_ser = Mock()
        mock_ser.is_open = True
        self.sender.ser = mock_ser
        
        with patch.object(self.sender, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': False, 'data': ''}
            
            result = self.sender.send_sms_message('+1234567890', 'Test')
            
            assert result['success'] is False
            assert result['data'] == ''
    
    def test_send_sms_message_no_prompt(self):
        """Test sending SMS when prompt is not received."""
        mock_ser = Mock()
        mock_ser.is_open = True
        mock_ser.reset_input_buffer = Mock()
        mock_ser.in_waiting = Mock(return_value=False)
        mock_ser.readline.return_value = b'\r\n'
        
        self.sender.ser = mock_ser
        
        with patch.object(self.sender, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': True, 'data': ''}
            
            result = self.sender.send_sms_message('+1234567890', 'Test')
            
            assert result['success'] is False
            assert 'prompt' in result['data'].lower() or result['data'] == ''
    
    def test_send_sms_message_send_fails(self):
        """Test sending SMS when send fails."""
        mock_ser = Mock()
        mock_ser.is_open = True
        mock_ser.reset_input_buffer = Mock()
        mock_ser.in_waiting = Mock(return_value=True)
        mock_ser.readline.side_effect = [
            b'> \r\n',  # Prompt received
            b'\r\n',
            b'ERROR\r\n'  # Error response
        ]
        
        self.sender.ser = mock_ser
        
        with patch.object(self.sender, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': True, 'data': ''}
            
            result = self.sender.send_sms_message('+1234567890', 'Test')
            
            assert result['success'] is False
    
    def test_send_sms_single_message(self):
        """Test sending a single SMS message."""
        with patch.object(self.sender, 'send_sms_message') as mock_send_msg:
            mock_send_msg.return_value = {'success': True, 'data': 'OK'}
            
            result = self.sender.send_sms('+1234567890', ['Hello World'])
            
            assert result is True
            mock_send_msg.assert_called_once_with('+1234567890', 'Hello World')
    
    def test_send_sms_multiple_messages(self):
        """Test sending multiple SMS messages."""
        with patch.object(self.sender, 'send_sms_message') as mock_send_msg, \
             patch('time.sleep'):
            mock_send_msg.side_effect = [
                {'success': True, 'data': 'OK'},
                {'success': True, 'data': 'OK'},
                {'success': True, 'data': 'OK'}
            ]
            
            messages = ['Message 1', 'Message 2', 'Message 3']
            result = self.sender.send_sms('+1234567890', messages)
            
            assert result is True
            assert mock_send_msg.call_count == 3
    
    def test_send_sms_partial_failure(self):
        """Test sending multiple messages with partial failure."""
        with patch.object(self.sender, 'send_sms_message') as mock_send_msg, \
             patch('time.sleep'):
            mock_send_msg.side_effect = [
                {'success': True, 'data': 'OK'},
                {'success': False, 'data': 'ERROR'},
                {'success': True, 'data': 'OK'}
            ]
            
            messages = ['Message 1', 'Message 2', 'Message 3']
            result = self.sender.send_sms('+1234567890', messages)
            
            assert result is False
            assert mock_send_msg.call_count == 3
    
    def test_send_sms_all_failures(self):
        """Test sending multiple messages where all fail."""
        with patch.object(self.sender, 'send_sms_message') as mock_send_msg, \
             patch('time.sleep'):
            mock_send_msg.return_value = {'success': False, 'data': 'ERROR'}
            
            messages = ['Message 1', 'Message 2']
            result = self.sender.send_sms('+1234567890', messages)
            
            assert result is False
    
    def test_send_sms_exception(self):
        """Test sending SMS when exception occurs."""
        with patch.object(self.sender, 'send_sms_message') as mock_send_msg:
            mock_send_msg.side_effect = Exception("Test exception")
            
            result = self.sender.send_sms('+1234567890', ['Test'])
            
            assert result is False
    
    def test_send_sms_message_with_unicode(self):
        """Test sending SMS with Unicode characters."""
        mock_ser = Mock()
        mock_ser.is_open = True
        mock_ser.reset_input_buffer = Mock()
        
        call_count = 0
        def in_waiting_side_effect():
            nonlocal call_count
            call_count += 1
            return call_count <= 8
        
        mock_ser.in_waiting = Mock(side_effect=in_waiting_side_effect)
        
        readline_responses = [
            b'\r\n',
            b'> \r\n',  # Prompt
            b'\r\n',
            b'+CMGS: 1\r\n',
            b'OK\r\n'
        ]
        readline_iterator = iter(readline_responses)
        
        def readline_side_effect():
            try:
                return next(readline_iterator)
            except StopIteration:
                return b'\r\n'
        
        mock_ser.readline.side_effect = readline_side_effect
        
        self.sender.ser = mock_ser
        
        with patch.object(self.sender, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': True, 'data': ''}
            
            # Test with Unicode message
            result = self.sender.send_sms_message('+1234567890', 'Привет! 😀')
            
            assert result['success'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


