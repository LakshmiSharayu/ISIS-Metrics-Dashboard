"""
ISIS Metrics Collector
Collects ISIS database metrics from Junos routers via SSH
"""

import logging
import re
import xml.etree.ElementTree as ET
from jnpr.junos import Device
from jnpr.junos.exception import ConnectError, RpcError
import yaml
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ISISCollector:
    """Collects ISIS metrics from Junos devices"""
    
    # ISIS metrics we're interested in
    METRICS = {
        'total_lsps': 'Total LSPs in database',
        'lsp_database_size': 'LSP Database Size (bytes)',
        'isis_nodes': 'Number of ISIS Nodes',
        'prefixes': 'Number of Prefixes',
        'database_overload': 'Database Overload Flag',
        'lsp_count_l1': 'L1 LSP Count',
        'lsp_count_l2': 'L2 LSP Count',
        'adjacencies': 'Total Adjacencies',
        'interfaces': 'ISIS Enabled Interfaces'
    }
    
    def __init__(self, config_file='config/devices.yml'):
        """Initialize collector with device configuration"""
        self.config_file = config_file
        self.devices_config = self._load_config()
        self.connections = {}
    
    def _load_config(self) -> Dict:
        """Load device configuration from YAML file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f) or {}
                    if config and 'hosts' in config:
                        logger.info(f"Loaded configuration for devices: {list(config['hosts'].keys())}")
                    return config
            logger.warning(f"Configuration file not found: {self.config_file}")
            return {}
        except Exception as e:
            logger.error(f"Error loading config file: {str(e)}")
            return {}
    
    def get_configured_devices(self) -> List[str]:
        """Get list of configured device hostnames"""
        devices = list(self.devices_config.get('hosts', {}).keys())
        logger.info(f"Configured devices: {devices}")
        return devices
    
    def add_device(self, device_name: str, host: str, username: str, password: str, 
                   port: int = 22, timeout: int = 30) -> bool:
        """
        Dynamically add a device configuration
        
        Args:
            device_name: Custom name for the device (e.g., 'core-router-1')
            host: IP address or hostname
            username: SSH username
            password: SSH password
            port: SSH port (default 22)
            timeout: Connection timeout in seconds
        
        Returns:
            True if device added successfully
        """
        try:
            if 'hosts' not in self.devices_config:
                self.devices_config['hosts'] = {}
            
            self.devices_config['hosts'][device_name] = {
                'host': host,
                'username': username,
                'password': password,
                'port': port,
                'timeout': timeout
            }
            
            logger.info(f"Device '{device_name}' added: {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"Error adding device '{device_name}': {str(e)}")
            return False
    
    def get_device_config(self, device_name: str) -> Optional[Dict]:
        """Get configuration for a specific device"""
        config = self.devices_config.get('hosts', {}).get(device_name)
        if not config:
            logger.warning(f"No configuration found for device: {device_name}")
            logger.info(f"Available devices: {list(self.devices_config.get('hosts', {}).keys())}")
        return config
    
    def _connect_to_device(self, device_name: str) -> Optional[Device]:
        """
        Establish SSH connection to Junos device
        Args:
            device_name: Device hostname or custom name
        Returns:
            Device object or None if connection fails
        """
        try:
            # Check if already connected
            if device_name in self.connections:
                if self.connections[device_name].connected:
                    return self.connections[device_name]
            
            # Get device configuration
            device_config = self.get_device_config(device_name)
            
            if not device_config:
                logger.error(f"No configuration found for device: {device_name}")
                logger.error(f"Please configure device in config/devices.yml or use add_device() method")
                return None
            
            # Establish connection
            dev = Device(
                host=device_config.get('host'),
                user=device_config.get('username'),
                password=device_config.get('password'),
                port=device_config.get('port', 22),
                timeout=device_config.get('timeout', 30)
            )
            
            dev.open()
            self.connections[device_name] = dev
            logger.info(f"Successfully connected to {device_name} ({device_config.get('host')})")
            return dev
        
        except ConnectError as e:
            logger.error(f"Connection error for {device_name}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error connecting to {device_name}: {str(e)}")
            return None
    
    def test_connection(self, device_name: str) -> Dict:
        """Test SSH connection to device"""
        dev = self._connect_to_device(device_name)
        if dev:
            return {
                'device': device_name,
                'connected': True,
                'status': 'Connection successful'
            }
        return {
            'device': device_name,
            'connected': False,
            'status': 'Connection failed'
        }
    
    def collect_metrics(self, device_name: str) -> Optional[Dict]:
        """
        Collect ISIS metrics from device
        Executes: show isis database extensive
        """
        dev = self._connect_to_device(device_name)
        if not dev:
            return None
        
        try:
            # Execute RPC to get ISIS database
            rpc_response = dev.rpc.request_shell_execute(
                command='show isis database extensive'
            )
            
            # Parse output
            metrics = self._parse_isis_output(rpc_response)
            metrics['device'] = device_name
            metrics['timestamp'] = datetime.utcnow().isoformat()
            
            logger.info(f"Successfully collected metrics from {device_name}")
            logger.info(f"Metrics: total_lsps={metrics['total_lsps']}, isis_nodes={metrics['isis_nodes']}, prefixes={metrics['prefixes']}")
            return metrics
        
        except RpcError as e:
            logger.error(f"RPC error on {device_name}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error collecting metrics from {device_name}: {str(e)}")
            return None
    
    def _parse_isis_output(self, output) -> Dict:
        """
        Parse ISIS database output and extract metrics
        
        Args:
            output: Raw output from 'show isis database extensive'
        
        Returns:
            Dictionary of parsed metrics
        """
        metrics = {
            'total_lsps': 0,
            'lsp_database_size': 0,
            'isis_nodes': 0,
            'prefixes': 0,
            'database_overload': False,
            'lsp_count_l1': 0,
            'lsp_count_l2': 0,
            'adjacencies': 0,
            'interfaces': 0,
            'raw_output': ''
        }
        
        try:
            # Convert output to string
            if hasattr(output, 'text'):
                output_text = output.text
            else:
                output_text = str(output)
            
            metrics['raw_output'] = output_text
            lines = output_text.split('\n')
            
            # Regex patterns for parsing
            lsp_pattern = re.compile(r'^([a-z0-9\-\.]+)\.([0-9a-f]{2})-([0-9a-f]{2})\s+Sequence:', re.IGNORECASE)
            level_pattern = re.compile(r'Level:\s*([12])')
            ip_prefix_pattern = re.compile(r'IP(?:v6)?\s+(?:extended\s+)?prefix:\s+([0-9a-f:.\/]+)', re.IGNORECASE)
            neighbor_pattern = re.compile(r'(?:IS\s+(?:extended\s+)?neighbor|IS neighbor):\s+([a-z0-9\-\.]+)', re.IGNORECASE)
            length_pattern = re.compile(r'Length:\s*(\d+)\s*bytes')
            adjacency_pattern = re.compile(r'(?:IS\s+(?:extended\s+)?neighbor|P2P\s+IP)', re.IGNORECASE)
            
            i = 0
            current_lsp_level = None
            
            while i < len(lines):
                line = lines[i].strip()
                
                # Parse LSP entries
                if lsp_pattern.match(line):
                    metrics['total_lsps'] += 1
                    
                    # Look ahead for level information
                    for j in range(i, min(i + 50, len(lines))):
                        level_match = level_pattern.search(lines[j])
                        if level_match:
                            level = int(level_match.group(1))
                            if level == 1:
                                metrics['lsp_count_l1'] += 1
                            elif level == 2:
                                metrics['lsp_count_l2'] += 1
                            break
                
                # Parse database size from LSP packets
                length_match = length_pattern.search(line)
                if length_match:
                    metrics['lsp_database_size'] += int(length_match.group(1))
                
                # Count prefixes (IP and IPv6)
                if ip_prefix_pattern.search(line):
                    metrics['prefixes'] += 1
                
                # Count neighbors/adjacencies
                if neighbor_pattern.search(line):
                    metrics['adjacencies'] += 1
                
                # Check for overload condition
                if 'Overload' in line or 'overload' in line:
                    metrics['database_overload'] = True
                
                i += 1
            
            # Calculate ISIS nodes (average of L1 and L2 LSP count)
            total_lsps = metrics['lsp_count_l1'] + metrics['lsp_count_l2']
            if total_lsps > 0:
                metrics['isis_nodes'] = max(metrics['lsp_count_l1'], metrics['lsp_count_l2'])
            
            logger.debug(f"Parsed metrics: {metrics}")
            return metrics
        
        except Exception as e:
            logger.error(f"Error parsing ISIS output: {str(e)}")
            return metrics
    
    def disconnect_all(self):
        """Close all device connections"""
        for device_name, dev in self.connections.items():
            try:
                dev.close()
                logger.info(f"Disconnected from {device_name}")
            except Exception as e:
                logger.warning(f"Error disconnecting from {device_name}: {str(e)}")
        self.connections.clear()
