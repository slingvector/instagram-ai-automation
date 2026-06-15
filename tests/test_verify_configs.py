import yaml
import os

def verify_configs():
    configs = [
        "config/creator_watchlist.yaml",
        "config/trending_sources.yaml"
    ]
    
    print("🏁 Starting Config Integrity Verification...")
    
    for config_path in configs:
        full_path = os.path.abspath(config_path)
        if not os.path.exists(full_path):
            print(f"❌ Missing config: {config_path}")
            continue
            
        try:
            with open(full_path, "r") as f:
                data = yaml.safe_load(f)
                print(f"✅ Syntactically valid: {config_path}")
                
                # Check for new niches
                if "creator_watchlist" in config_path:
                    keys = data.get("creators", {}).keys()
                    print(f"   Found niches: {list(keys)}")
                    if "sports_racing" in keys and "ai_robotics_drones" in keys:
                        print("   ✅ New niches found in watchlist.")
                    if "beauty_fashion" in keys:
                        print("   ❌ Fashion STILL present in watchlist!")
                
                if "trending_sources" in config_path:
                    sources = data.get("sources", {})
                    print(f"   Has {len(sources.get('instagram_pages', []))} IG sources, {len(sources.get('reddit', []))} subreddits.")
                    if any("f1" in str(s) for s in sources.get("instagram_pages", [])):
                        print("   ✅ Racing sources confirmed.")
                    if any("fashion" in str(s) for s in sources.get("reddit", [])):
                         print("   ❌ Fashion STILL present in subreddits!")

        except Exception as e:
            print(f"❌ Failed to parse {config_path}: {e}")

if __name__ == "__main__":
    verify_configs()
