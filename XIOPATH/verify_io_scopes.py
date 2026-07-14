import sys
import json
from core.memory_manager import MemoryManager

def run_test():
    print("Initializing Memory Manager...")
    manager = MemoryManager(session_id="test_session_io")
    
    print("\n--- Test 1: Static Vault Input (Fill Password) ---")
    face_val_1 = {"description": "Password Field", "text": ""}
    place_val_1 = {"selector": "#password"}
    action_params_1 = {"text": "vault://github_pass"}
    
    manager.save_new_action(
        url="https://github.com/login",
        intent="test_vault_input",
        face_value=face_val_1,
        place_value=place_val_1,
        action_type="fill",
        action_params=action_params_1,
        volatility_type="static"
    )
    
    print("\n--- Test 2: Dynamic Plugin Input + Output (Solve Captcha) ---")
    face_val_2 = {"description": "Captcha Container", "text": ""}
    place_val_2 = {"selector": "#captcha"}
    
    manager.save_new_action(
        url="https://github.com/login",
        intent="test_plugin_input",
        face_value=face_val_2,
        place_value=place_val_2,
        action_type="extract_data",
        action_params={},
        volatility_type="dynamic",
        fallback_plugin="2captcha_solver",
        output_var="captcha_token"
    )
    
    print("\n--- Verification ---")
    import sqlite3
    conn = sqlite3.connect("data/memory.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT intent, face_value, place_value FROM memory_nodes WHERE intent IN ('test_vault_input', 'test_plugin_input')")
    rows = cursor.fetchall()
    
    assert len(rows) == 2, "Failed to retrieve both test nodes."
    
    for intent, fv_str, pv_str in rows:
        fv = json.loads(fv_str)
        pv = json.loads(pv_str)
        
        print(f"\nEvaluating Node: {intent}")
        print(f"FACE Value Semantic Input: {fv['semantic_input']}")
        print(f"PLACE Value Structural Input: {pv['structural_input']}")
        
        if intent == "test_vault_input":
            assert fv['semantic_input']['volatility'] == 'static'
            assert fv['semantic_input']['requires_data'] == True
            assert pv['structural_input']['source_type'] == 'vault'
            assert pv['structural_output']['destination_type'] == 'none'
        
        if intent == "test_plugin_input":
            assert fv['semantic_input']['volatility'] == 'dynamic'
            assert fv['semantic_input']['requires_data'] == True
            assert pv['structural_input']['source_type'] == 'runtime_plugin'
            assert pv['structural_output']['destination_type'] == 'workflow_var'
            assert pv['structural_output']['destination_key'] == 'captcha_token'
            assert fv['semantic_output']['produces_data'] == True

    print("\n✅ Verification Successful! I/O Scopes perfectly embedded.")
    
    # Clean up
    cursor.execute("DELETE FROM memory_nodes WHERE intent IN ('test_vault_input', 'test_plugin_input')")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    run_test()
