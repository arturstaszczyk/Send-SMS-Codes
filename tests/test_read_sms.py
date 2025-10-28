#!/usr/bin/env python3
"""
Unit tests for SMS reading functionality.
"""

import pytest
import serial
import time
from unittest.mock import Mock, patch
from io import BytesIO

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.read_sms import SMSReader


class TestSMSReader:
    """Test suite for SMSReader class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.reader = SMSReader(port='/dev/ttyS0', baudrate=115200, timeout=1)
    
    def test_init(self):
        """Test SMSReader initialization."""
        assert self.reader.port == '/dev/ttyS0'
        assert self.reader.baudrate == 115200
        assert self.reader.timeout == 1
    
    def test_list_all_sms_no_messages(self):
        """Test listing SMS when no messages exist."""
        with patch.object(self.reader, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {'success': True, 'data': ''},  # CMGF=1
                {'success': True, 'data': ''}   # CMGL="ALL" - empty
            ]
            
            messages = self.reader.list_all_sms()
            
            assert messages == []
            assert mock_send.call_count == 2
    
    def test_list_all_sms_with_messages(self):
        """Test listing SMS with messages."""
        mock_sms_data = '''+CMGL: 0,"REC UNREAD","+1234567890","23/10/15,10:20:30+00"
Hello World
+CMGL: 1,"REC READ","+9876543210","23/10/15,11:30:45+00"
Test message'''
        
        with patch.object(self.reader, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {'success': True, 'data': ''},  # CMGF=1
                {'success': True, 'data': mock_sms_data}  # CMGL="ALL"
            ]
            
            messages = self.reader.list_all_sms()
            
            assert len(messages) == 2
            assert messages[0]['index'] == '0'
            assert messages[0]['status'] == 'REC UNREAD'
            assert messages[0]['sender'] == '+1234567890'
            assert messages[0]['content'] == 'Hello World'
            assert messages[1]['index'] == '1'
            assert messages[1]['status'] == 'REC READ'
    
    def test_list_all_sms_cmgf_fails(self):
        """Test listing SMS when CMGF fails."""
        with patch.object(self.reader, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': False, 'data': ''}
            
            messages = self.reader.list_all_sms()
            
            assert messages is None
    
    def test_list_all_sms_cmgl_fails(self):
        """Test listing SMS when CMGL fails."""
        with patch.object(self.reader, 'send_at_command') as mock_send:
            mock_send.side_effect = [
                {'success': True, 'data': ''},  # CMGF=1
                {'success': False, 'data': ''}  # CMGL="ALL" - fails
            ]
            
            messages = self.reader.list_all_sms()
            
            assert messages is None
    
    def test_parse_sms_messages_single(self):
        """Test parsing single SMS message."""
        data = '''+CMGL: 0,"REC UNREAD","+1234567890","23/10/15,10:20:30+00"
Hello World'''
        
        messages = self.reader.parse_sms_messages(data)
        
        assert len(messages) == 1
        assert messages[0]['index'] == '0'
        assert messages[0]['status'] == 'REC UNREAD'
        assert messages[0]['sender'] == '+1234567890'
        assert messages[0]['timestamp'] == '23/10/15,10:20:30+00'
        assert messages[0]['content'] == 'Hello World'
    
    def test_parse_sms_messages_multiple(self):
        """Test parsing multiple SMS messages."""
        data = '''+CMGL: 0,"REC UNREAD","+1234567890","23/10/15,10:20:30+00"
First message
+CMGL: 1,"REC READ","+9876543210","23/10/15,11:30:45+00"
Second message'''
        
        messages = self.reader.parse_sms_messages(data)
        
        assert len(messages) == 2
        assert messages[0]['content'] == 'First message'
        assert messages[1]['content'] == 'Second message'
    
    def test_parse_sms_messages_empty(self):
        """Test parsing empty SMS data."""
        messages = self.reader.parse_sms_messages('')
        
        assert messages == []
    
    def test_parse_sms_messages_unicode_encoded(self):
        """Test parsing Unicode-encoded SMS message."""
        # Test the Unicode hex decoding logic
        data = '''+CMGL: 0,"REC UNREAD","+1234567890","23/10/15,10:20:30+00"
00480065006C006C006F00200057006F0072006C0064'''  # "Hello World" in UCS2/UTF-16BE hex
        
        messages = self.reader.parse_sms_messages(data)
        
        assert len(messages) == 1
        # The content should be the hex string before decoding in the parser
        # The decoding happens in the printing logic, not in the parser
        assert messages[0]['content'] == '00480065006C006C006F00200057006F0072006C0064'
    
    def test_delete_sms_success(self):
        """Test deleting SMS successfully."""
        with patch.object(self.reader, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': True, 'data': ''}
            
            result = self.reader.delete_sms('0')
            
            assert result is True
            mock_send.assert_called_once_with('AT+CMGD=0')
    
    def test_delete_sms_failure(self):
        """Test deleting SMS failure."""
        with patch.object(self.reader, 'send_at_command') as mock_send:
            mock_send.return_value = {'success': False, 'data': ''}
            
            result = self.reader.delete_sms('0')
            
            assert result is False
    
    def test_read_and_connect_success(self):
        """Test complete SMS reading flow success."""
        with patch.object(self.reader, 'connect') as mock_connect, \
             patch.object(self.reader, 'disconnect') as mock_disconnect, \
             patch.object(self.reader, 'send_at_command') as mock_send, \
             patch.object(self.reader, 'detect_baudrate'), \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            
            mock_send.side_effect = [
                {'success': True, 'data': ''},  # ATE0
                {'success': True, 'data': ''},  # CMGF=1
                {'success': True, 'data': ''}   # CMGL="ALL"
            ]
            
            result = self.reader.read_and_connect()
            
            assert result is True
            mock_connect.assert_called_once()
            mock_disconnect.assert_called_once()
    
    def test_read_and_connect_connection_failure(self):
        """Test SMS reading when connection fails."""
        with patch.object(self.reader, 'connect') as mock_connect:
            mock_connect.return_value = False
            
            result = self.reader.read_and_connect()
            
            assert result is False
    
    def test_read_and_connect_with_messages(self):
        """Test SMS reading with actual messages."""
        mock_sms_data = '''+CMGL: 0,"REC UNREAD","+1234567890","23/10/15,10:20:30+00"
Hello World'''
        
        with patch.object(self.reader, 'connect') as mock_connect, \
             patch.object(self.reader, 'disconnect') as mock_disconnect, \
             patch.object(self.reader, 'send_at_command') as mock_send, \
             patch.object(self.reader, 'detect_baudrate'), \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            
            mock_send.side_effect = [
                {'success': True, 'data': ''},      # ATE0
                {'success': True, 'data': ''},      # CMGF=1
                {'success': True, 'data': mock_sms_data}  # CMGL="ALL"
            ]
            
            result = self.reader.read_and_connect()
            
            assert result is True
            mock_connect.assert_called_once()
    
    def test_read_and_connect_list_fails(self):
        """Test SMS reading when list_all_sms fails."""
        with patch.object(self.reader, 'connect') as mock_connect, \
             patch.object(self.reader, 'disconnect') as mock_disconnect, \
             patch.object(self.reader, 'send_at_command') as mock_send, \
             patch.object(self.reader, 'detect_baudrate'), \
             patch('time.sleep'):
            
            mock_connect.return_value = True
            
            mock_send.side_effect = [
                {'success': True, 'data': ''},      # ATE0
                {'success': False, 'data': ''}     # CMGF=1 fails
            ]
            
            result = self.reader.read_and_connect()
            
            assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

