import hashlib
import json
from typing import List, Dict, Any, Set
from app.models.drift import SemanticDrift
from app.models.plan_operation import PlanOperation
from app.drivers.errors import ValidationError

class PlanGenerator:
    @staticmethod
    def generate_operations(device_id: str, drifts: List[SemanticDrift]) -> List[PlanOperation]:
        ops = []
        for drift in drifts:
            if drift.attribute == "vlan":
                ops.append(PlanOperation(
                    device_id=device_id,
                    operation_type="CREATE_VLAN",
                    old_value=drift.old_value,
                    new_value=drift.new_value,
                    risk="LOW"
                ))
            elif drift.attribute in ("interface_mode", "interface_access_vlan"):
                ops.append(PlanOperation(
                    device_id=device_id,
                    operation_type="SET_ACCESS_VLAN",
                    interface=drift.key,
                    old_value=drift.old_value,
                    new_value=drift.new_value,
                    risk="HIGH"
                ))
            elif drift.attribute == "interface_trunk_vlans":
                ops.append(PlanOperation(
                    device_id=device_id,
                    operation_type="ADD_TRUNK_VLAN",
                    interface=drift.key,
                    old_value=drift.old_value,
                    new_value=drift.new_value,
                    risk="MEDIUM"
                ))
        return ops

    @staticmethod
    def build_dag_and_sort(operations: List[PlanOperation]) -> List[PlanOperation]:
        # 1. Map operations by ID and type for dependency lookup
        op_map = {op.operation_id: op for op in operations}
        
        # Build dependencies dynamically
        for op in operations:
            if op.operation_type in ("SET_ACCESS_VLAN", "ADD_TRUNK_VLAN"):
                # Depends on CREATE_VLAN for the same vlan_id on the same switch
                target_vlan = op.new_value
                if isinstance(target_vlan, list) and len(target_vlan) > 0:
                    target_vlan = target_vlan[0]
                
                for other in operations:
                    if (other.device_id == op.device_id and 
                        other.operation_type == "CREATE_VLAN" and 
                        other.new_value == target_vlan):
                        op.dependencies.append(other.operation_id)

        # 2. Topological sort using Kahn's algorithm or DFS
        # We also need cycle detection
        adj = {op.operation_id: set(op.dependencies) for op in operations}
        
        # Cycle detection using DFS
        visited = {} # 0 = unvisited, 1 = visiting, 2 = visited
        for op_id in adj:
            visited[op_id] = 0
            
        def dfs_cycle(u: str) -> bool:
            visited[u] = 1
            for v in adj[u]:
                if visited.get(v, 0) == 1:
                    return True
                if visited.get(v, 0) == 0:
                    if dfs_cycle(v):
                        return True
            visited[u] = 2
            return False

        for op_id in adj:
            if visited[op_id] == 0:
                if dfs_cycle(op_id):
                    raise ValidationError("DEPENDENCY_CYCLE: Espera circular de dependencias detectada no plano.")

        # Perform topological sort
        sorted_ids = []
        visited_sort = set()
        
        def visit(u: str):
            if u not in visited_sort:
                for v in adj[u]:
                    visit(v)
                visited_sort.add(u)
                sorted_ids.append(u)

        for op_id in adj:
            visit(op_id)
            
        return [op_map[oid] for oid in sorted_ids]

    @staticmethod
    def compute_plan_hash(operations: List[PlanOperation]) -> str:
        # Sort operations by ID to guarantee determinism
        sorted_ops = sorted(operations, key=lambda x: x.operation_id)
        serialized_ops = [op.to_dict() for op in sorted_ops]
        plan_str = json.dumps(serialized_ops, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(plan_str.encode('utf-8')).hexdigest()
