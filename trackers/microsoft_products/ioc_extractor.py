"""
IOC Extractor module for the CTI Aggregator.
Extracts Indicators of Compromise (IOCs) from text.
"""

import re
import logging
import ipaddress

logger = logging.getLogger(__name__)

class IOCExtractor:
    """Extracts various types of IOCs from text"""
    
    def __init__(self):
        """Initialize the IOC extractor with regex patterns"""
        # IP address pattern - matches IPv4 addresses
        self.ip_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        
        # Domain pattern - matches domain names
        self.domain_pattern = r'\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]\b'
        
        # URL pattern - matches URLs
        self.url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
        
        # MD5 hash pattern - 32 hex characters
        self.md5_pattern = r'\b[a-fA-F0-9]{32}\b'
        
        # SHA1 hash pattern - 40 hex characters
        self.sha1_pattern = r'\b[a-fA-F0-9]{40}\b'
        
        # SHA256 hash pattern - 64 hex characters
        self.sha256_pattern = r'\b[a-fA-F0-9]{64}\b'
        
        # Email pattern
        self.email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        # CVE pattern - matches CVE IDs (e.g., CVE-2021-12345)
        self.cve_pattern = r'CVE-\d{4}-\d{4,7}'
        
        # Registry key pattern
        self.registry_pattern = r'HKEY_[A-Z_]+(?:\\[A-Za-z0-9_]+)+'
        
        # File path pattern - basic Windows and Unix paths
        self.file_path_pattern = r'(?:[a-zA-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*|/(?:[^/\0]+/)*[^/\0]*)'
        
        # MITRE ATT&CK technique ID pattern (e.g., T1566, T1566.001)
        self.mitre_pattern = r'T\d{4}(?:\.\d{3})?'
        
        # User agent string pattern - common in Volexity reports
        self.user_agent_pattern = r'Mozilla/[0-9.]+ \([^)]+\) [^"]+'
        
        # Cryptocurrency wallet address patterns
        self.btc_address_pattern = r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b'
        self.eth_address_pattern = r'\b0x[a-fA-F0-9]{40}\b'
        
        # Yara rule name pattern
        self.yara_rule_pattern = r'\brule\s+[a-zA-Z0-9_]+\s*{'
        
        # Initialize patterns list for easy iteration
        self.patterns = {
            'ip': self.ip_pattern,
            'domain': self.domain_pattern,
            'url': self.url_pattern,
            'md5': self.md5_pattern,
            'sha1': self.sha1_pattern,
            'sha256': self.sha256_pattern,
            'email': self.email_pattern,
            'cve': self.cve_pattern,
            'registry': self.registry_pattern,
            'file_path': self.file_path_pattern,
            'mitre_technique': self.mitre_pattern,
            'user_agent': self.user_agent_pattern,
            'btc_address': self.btc_address_pattern,
            'eth_address': self.eth_address_pattern,
            'yara_rule': self.yara_rule_pattern
        }
        
        # List of common false positives to filter out
        self.false_positives = {
            'ip': [
                '0.0.0.0', '127.0.0.1', '255.255.255.255', 
                '1.1.1.1', '8.8.8.8', '8.8.4.4'
            ],
            'domain': [
                'example.com', 'domain.com', 'website.com', 
                'google.com', 'microsoft.com', 'apple.com',
                'facebook.com', 'twitter.com', 'github.com'
            ],
            'md5': [
                '00000000000000000000000000000000',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'ffffffffffffffffffffffffffffffff'
            ],
            'sha1': [
                '0000000000000000000000000000000000000000',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'ffffffffffffffffffffffffffffffffffffffff'
            ],
            'sha256': [
                '0000000000000000000000000000000000000000000000000000000000000000',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'
            ]
        }
    
    def extract_from_text(self, text):
        """
        Extract all IOCs from text.
        
        Args:
            text (str): Text to extract IOCs from
        
        Returns:
            dict: Dictionary of IOCs by type
                {
                    'ip': [{'value': '1.2.3.4', 'context': 'surrounding text'}],
                    'domain': [...],
                    ...
                }
        """
        if not text:
            return {}
        
        results = {}
        
        # Extract each type of IOC
        for ioc_type, pattern in self.patterns.items():
            matches = self.extract_with_context(text, pattern)
            
            # Filter out false positives
            filtered_matches = []
            for match in matches:
                value = match['value']
                
                # Skip if it's in our false positives list
                if ioc_type in self.false_positives and value in self.false_positives[ioc_type]:
                    continue
                
                # Additional validation for specific IOC types
                if ioc_type == 'ip' and not self.is_valid_ip(value):
                    continue
                elif ioc_type == 'domain' and (
                    '.' not in value or 
                    any(c in value for c in ['[', ']', '(', ')', '{', '}'])
                ):
                    continue
                elif ioc_type in ['md5', 'sha1', 'sha256'] and not self.is_likely_hash(value):
                    continue
                
                filtered_matches.append(match)
            
            if filtered_matches:
                results[ioc_type] = filtered_matches
        
        return results
    
    def extract_with_context(self, text, pattern, context_size=50):
        """
        Extract IOCs along with surrounding context.
        
        Args:
            text (str): Text to extract from
            pattern (str): Regex pattern
            context_size (int): Number of characters to include as context
        
        Returns:
            list: List of dictionaries with 'value' and 'context'
        """
        results = []
        matches = re.finditer(pattern, text)
        
        for match in matches:
            value = match.group(0)
            
            # Get context around the match
            start = max(0, match.start() - context_size)
            end = min(len(text), match.end() + context_size)
            
            # Extract context and highlight the match
            context = text[start:match.start()] + "[" + value + "]" + text[match.end():end]
            
            # Clean up context (remove newlines, etc.)
            context = ' '.join(context.split())
            
            results.append({
                'value': value,
                'context': context
            })
        
        return results
    
    def is_valid_ip(self, ip_str):
        """
        Validate if a string is a valid IPv4 address.
        
        Args:
            ip_str (str): String to validate
        
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            # Check if it's a valid IP address
            ip = ipaddress.ip_address(ip_str)
            
            # Filter out private, loopback, and multicast addresses
            if ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_unspecified:
                return False
                
            return True
        except ValueError:
            return False
    
    def is_likely_hash(self, hash_str):
        """
        Check if a string is likely to be a hash.
        
        Args:
            hash_str (str): String to check
        
        Returns:
            bool: True if likely a hash, False otherwise
        """
        # Check if it's all hex digits
        if not all(c in '0123456789abcdefABCDEF' for c in hash_str):
            return False
        
        # Check if it has a reasonable distribution of characters
        # (real hashes should have a somewhat random distribution)
        character_count = {}
        for c in hash_str.lower():
            if c in character_count:
                character_count[c] += 1
            else:
                character_count[c] = 1
        
        # If any character appears more than 50% of the time, it's suspicious
        hash_length = len(hash_str)
        for count in character_count.values():
            if count > hash_length * 0.5:
                return False
        
        return True
