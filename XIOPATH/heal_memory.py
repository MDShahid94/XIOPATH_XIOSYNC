import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core'))
from memory_manager import MemoryManager

def heal_memory():
    mgr = MemoryManager("mcp-agent-session")
    action = mgr.lookup_action("https://www.saucedemo.com/inventory.html", "add_to_cart")
    
    # Heal the place value
    new_place_value = action["place_value"].copy()
    new_place_value["selector"] = "#broken-id"
    
    mgr.save_new_action(
        url="https://www.saucedemo.com/inventory.html",
        intent="add_to_cart",
        face_value=action["face_value"],
        place_value=new_place_value,
        action_type=action["action_type"],
        action_params=action["action_params"]
    )
    print("Memory healed!")

if __name__ == "__main__":
    heal_memory()
