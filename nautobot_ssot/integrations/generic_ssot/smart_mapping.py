"""Smart DCIM field mapping using DiffSync/contrib patterns."""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from diffsync import Adapter
from diffsync.enum import DiffSyncFlags

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device, Interface
from nautobot.ipam.models import VLAN

logger = logging.getLogger("nautobot.ssot")


class DCIMPatternDetector:
    """Detects DCIM data patterns and maps to DiffSync/contrib models."""
    
    DCIM_FIELD_PATTERNS = {
        'device': {
            'name': [
                'hostname', 'name', 'device_name', 'sys_name', 'label', 'device_id', 'host'
            ],
            'serial': [
                'serial', 'serial_no', 'serial_number', 'chassis_serial', 'hardware_serial'
            ],
            'asset_tag': [
                'asset_tag', 'asset_id', 'tag', 'identifier', 'rack_tag'
            ],
            'status': [
                'status', 'state', 'device_status', 'operational_status', 'power_state'
            ],
            'primary_ip': [
                'ip_address', 'primary_ip', 'ip', 'management_ip', 'mgmt_ip', 'address'
            ],
            'of_type': [
                'platform', 'os', 'operating_system', 'device_type', 'system'
            ]
        },
        'interface': {
            'name': [
                'interface', 'port', 'if_name', 'ifname', 'port_name', 'interface_name'
            ],
            'mac_address': [
                'mac', 'mac_address', 'hardware_address', 'physical_address', 'macaddr'
            ],
            'speed': [
                'speed', 'bandwidth', 'capacity', 'if_speed', 'interface_speed', 'port_speed'
            ],
            'status': [
                'port_status', 'link_status', 'operational_status', 'port_state', 'admin_status'
            ],
            'mtu': [
                'mtu', 'max_transmission_unit', 'packet_size'
            ]
        },
        'vlan': {
            'vid': [
                'vlan_id', 'vid', 'vlan_number', 'tag', 'vlan_tag'
            ],
            'name': [
                'vlan_name', 'name', 'description_vlan', 'vlan_description'
            ],
            'status': [
                'vlan_status', 'enabled', 'active_vlan', 'vlan_state'
            ]
        }
    }

    STATUS_MAPPINGS = {
        'active': ['up', 'online', 'alive', '1', 'active', 'enabled', 'ok', 'working'],
        'offline': ['down', 'offline', '0', 'decommissioned', 'disabled', 'offline'],
        'planned': ['planned', 'staged', 'pending', 'new'],
        'failed': ['failed', 'error', 'faulty', 'degraded']
    }

    def __init__(self, sample_data: List[Dict[str, Any]]):
        """Initialize with sample API data."""
        self.sample_data = sample_data
        self.confidence_scores = {}

    def detect_dcim_model(self, model_class) -> str:
        """Map Django model to DCIM pattern key."""
        model_map = {
            'Device': 'device',
            'Interface': 'interface', 
            'VLAN': 'vlan'
        }
        return model_map.get(model_class.__name__, 'generic')

    def suggest_mappings(self, model_class) -> Dict[str, List[Tuple[str, int]]]:
        """Suggest DCIM field mappings using contrib model requirements."""
        model_key = self.detect_dcim_model(model_class)
        if not self.sample_data:
            return {}
            
        # Build candidate mappings
        candidates = {}
        patterns = self.DCIM_FIELD_PATTERNS.get(model_key, {})
        
        # Scan sample data for fields
        all_fields = set()
        for record in self.sample_data[:10]:  # Use reasonable sample
            all_fields.update(record.keys())
        
        # Match patterns to available fields
        for dcim_field, possible_source_fields in patterns.items():
            matches = []
            for source_field in all_fields:
                matching_score = self._calculate_similarity(source_field, possible_source_fields)
                if matching_score > 0:
                    matches.append((source_field, matching_score))
                    
            # Sort by confidence score (highest first)
            matches.sort(key=lambda x: x[1], reverse=True)
            candidates[dcim_field] = matches[:3]  # Top 3 suggestions
            
        return candidates

    def _calculate_similarity(self, source_field: str, target_patterns: List[str]) -> int:
        """Calculate similarity score between source field and target patterns."""
        source = source_field.lower().replace('_', '').replace(' ', '')
        
        scores = []
        for pattern in target_patterns:
            pattern = pattern.lower().replace('_', '').replace(' ', '')
            
            # Exact match
            if source == pattern:
                return 100
                
            # Contains match
            if pattern in source or source in pattern:
                return 80
                
            # Partial string similarity
            similarity = self._string_similarity(source, pattern)
            if similarity > 0.7:
                scores.append(int(similarity * 70))
                
        return max(scores) if scores else 0

    def _string_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity using Levenshtein-like approach."""
        if not str1 or not str2:
            return 0.0
            
        str1, str2 = str1.lower(), str2.lower()
        longer = max(str1, str2, key=len)
        shorter = min(str1, str2, key=len)
        
        if len(longer) == 0:
            return 1.0
            
        return (len(longer) - self._edit_distance(longer, shorter)) / len(longer)

    def _edit_distance(self, s1: str, s2: str) -> int:
        """Calculate edit distance between two strings."""
        if len(s1) > len(s2):
            s1, s2 = s2, s1
            
        distances = list(range(len(s1) + 1))
        for i2, c2 in enumerate(s2):
            distances_ = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
        return distances[-1]

    def build_status_mapping(self, source_status_field: str) -> Dict[str, str]:
        """Create status value mapping using common DCIM patterns."""
        status_values = []
        for record in self.sample_data:
            if source_status_field in record:
                status_values.append(str(record[source_status_field]).lower())
                
        value_map = {}
        for value in set(status_values):
            for target_status, source_patterns in self.STATUS_MAPPINGS.items():
                if value in source_patterns:
                    value_map[value] = target_status
                    break
                    
        # Fallback for unmatched values
        for value in set(status_values) - set(value_map.keys()):
            value_map[value] = 'scheduled'
            
        return value_map


class SmartGenericAdapter(Adapter):
    """Smart adapter using AI patterns within existing DiffSync structure."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_mappings = {}
        self.confidence_scores = {}
        
    def auto_configure_mapping(self, sample_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Auto-configure field mappings based on detected DCIM patterns."""
        detector = DCIMPatternDetector(sample_data)
        
        # Map to your model classes using contrib patterns
        model_mappings = {}
        for model_field_name in self.get_all_diffsync_model_names():
            model_class = self.get_model_class(model_field_name)
            mappings = detector.suggest_mappings(model_class)
            model_mappings[model_field_name] = mappings
            
        return {
            'mappings': model_mappings,
            'status_mappings': self._extract_status_mappings(sample_data),
            'confidence_summary': self._calculate_confidence_summary()
        }

    def _extract_status_mappings(self, sample_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """Extract status value mappings for detected status fields."""
        mappings = {}
        detector = DCIMPatternDetector(sample_data)
        
        for model_name, model_class in self.get_all_diffsync_models().items():
            status_mappings = detector.build_status_mapping('status')
            if status_mappings:
                mappings[model_name] = status_mappings
                
        return mappings

    def validate_mapping_confidence(self, mapping: Dict[str, Any]) -> Dict[str, int]:
        """Return confidence scores for each mapping decision."""
        scores = {}
        for model_name, field_mappings in mapping['mappings'].items():
            for field, suggestions in field_mappings.items():
                if suggestions:
                    scores[f"{model_name}.{field}"] = suggestions[0][1]  # Highest confidence
                else:
                    scores[f"{model_name}.{field}"] = 0
                    
        return scores