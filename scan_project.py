#!/usr/bin/env python3
"""
Project scanner to inventory all user-defined functions and classes
for test generation purposes.
"""

import inspect
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

def load_module_from_path(module_path: Path, module_name: str):
    """Load a Python module from file path"""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return None
    
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"Warning: Could not load {module_path}: {e}")
        return None

def is_user_defined(obj, module_name: str) -> bool:
    """Check if object is user-defined (not imported from third-party)"""
    if not hasattr(obj, '__module__'):
        return False
    
    obj_module = obj.__module__
    if obj_module is None:
        return False
    
    # Include objects from current module or local modules
    return (obj_module == module_name or 
            obj_module.startswith('__main__') or
            not ('.' in obj_module and obj_module.split('.')[0] in [
                'flask', 'werkzeug', 'logging', 'os', 'sys', 'json', 'csv', 
                're', 'datetime', 'functools', 'typing', 'pathlib'
            ]))

def scan_module(module_path: Path) -> Dict[str, List[Tuple[str, Any]]]:
    """Scan a module and return all user-defined functions and classes"""
    module_name = module_path.stem
    module = load_module_from_path(module_path, module_name)
    
    if module is None:
        return {"functions": [], "classes": []}
    
    functions = []
    classes = []
    
    for name, obj in inspect.getmembers(module):
        # Skip dunder methods and private methods
        if name.startswith('_'):
            continue
            
        # Skip non-user-defined objects
        if not is_user_defined(obj, module_name):
            continue
        
        if inspect.isfunction(obj):
            functions.append((name, obj))
        elif inspect.isclass(obj):
            classes.append((name, obj))
            
            # Scan class methods
            for method_name, method_obj in inspect.getmembers(obj):
                if (method_name.startswith('_') and 
                    not method_name in ['__init__', '__str__', '__repr__']):
                    continue
                    
                if inspect.isfunction(method_obj) or inspect.ismethod(method_obj):
                    functions.append((f"{name}.{method_name}", method_obj))
    
    return {"functions": functions, "classes": classes}

def scan_project() -> Dict[str, Dict[str, List[Tuple[str, Any]]]]:
    """Scan entire project for user-defined functions and classes"""
    project_root = Path('.')
    results = {}
    
    # Core module files to scan
    module_files = [
        'app.py',
        'main.py', 
        'routes.py',
        'storage.py',
        'models.py',
        'auth.py'
    ]
    
    for module_file in module_files:
        module_path = project_root / module_file
        if module_path.exists():
            print(f"Scanning {module_file}...")
            results[module_file] = scan_module(module_path)
    
    return results

def print_inventory(results: Dict[str, Dict[str, List[Tuple[str, Any]]]]):
    """Print the inventory in a readable format"""
    print("\n" + "="*60)
    print("PROJECT INVENTORY")
    print("="*60)
    
    total_functions = 0
    total_classes = 0
    
    for module_name, items in results.items():
        print(f"\n📁 {module_name}")
        
        if items["classes"]:
            print("  Classes:")
            for class_name, class_obj in items["classes"]:
                print(f"    • {class_name}")
                total_classes += 1
        
        if items["functions"]:
            print("  Functions:")
            for func_name, func_obj in items["functions"]:
                try:
                    sig = inspect.signature(func_obj)
                    print(f"    • {func_name}{sig}")
                except (ValueError, TypeError):
                    print(f"    • {func_name}(...)")
                total_functions += 1
    
    print(f"\n📊 SUMMARY")
    print(f"   Total Classes: {total_classes}")
    print(f"   Total Functions: {total_functions}")
    print("="*60)

if __name__ == "__main__":
    results = scan_project()
    print_inventory(results)
    
    # Save results for test generation
    import json
    with open('project_inventory.json', 'w') as f:
        # Convert objects to serializable format
        serializable_results = {}
        for module_name, items in results.items():
            serializable_results[module_name] = {
                'functions': [(name, None) for name, obj in items['functions']],
                'classes': [(name, None) for name, obj in items['classes']]
            }
        json.dump(serializable_results, f, indent=2)
    
    print(f"\n💾 Inventory saved to project_inventory.json")