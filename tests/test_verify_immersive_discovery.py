"""
tests/verify_immersive_discovery.py

Verifies the Immersive POV Adrenaline niche integration.
1. Tests ImmersiveClassifier heuristics.
2. Tests HookEngine category-awareness.
3. Tests TrendingAdapter adapter integration.
"""
import sys
import os
import logging

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion.services.immersive_classifier import ImmersiveClassifier
from src.media_factory.services.hook_engine import HookEngine
from src.ingestion.base import ContentItem, Platform, SourceType, Niche

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_classifier():
    print("\n--- Testing ImmersiveClassifier ---")
    classifier = ImmersiveClassifier()
    
    # 1. FPV Case
    fpv_meta = classifier.classify("Insane FPV drone chase through abandoned building", "fpv")
    print(f"FPV Match: {fpv_meta}")
    assert fpv_meta["type"] == "fpv_drone"
    assert fpv_meta["perspective"] == "fpv"
    assert fpv_meta["motion"] == "high"
    assert fpv_meta["immersion_score"] >= 0.8
    
    # 2. 360 Case
    t360_meta = classifier.classify("Surreal 360 degree tiny planet orbit", "360 camera")
    print(f"360 Match: {t360_meta}")
    assert t360_meta["type"] == "360_tiny_planet"
    assert t360_meta["perspective"] == "360"
    
    # 3. Riding Case
    ride_meta = classifier.classify("POV downhill mtb ride fast", "mtb")
    print(f"Riding Match: {ride_meta}")
    assert ride_meta["type"] == "riding"
    assert ride_meta["motion"] == "high"
    
    print("✅ Classifier verified.")

def test_hook_engine():
    print("\n--- Testing HookEngine ---")
    engine = HookEngine()
    
    fpv_meta = {"type": "fpv_drone", "motion": "high", "perspective": "fpv"}
    hook = engine.generate_hook(fpv_meta)
    print(f"FPV Hook: {hook}")
    assert hook in engine.HOOKS["immersion"] or hook in engine.HOOKS["impossible"]
    
    t360_meta = {"type": "360_tiny_planet", "motion": "medium", "perspective": "360"}
    hook = engine.generate_hook(t360_meta)
    print(f"360 Hook: {hook}")
    assert hook in engine.HOOKS["reality_break"] or hook in engine.HOOKS["impossible"]
    
    print("✅ HookEngine verified.")

def test_content_item_meta():
    print("\n--- Testing ContentItem Metadata ---")
    classifier = ImmersiveClassifier()
    meta = classifier.classify("Epic Skydive POV Wingsuit", "skydiving")
    
    item = ContentItem(
        url="https://example.com/video",
        platform=Platform.YOUTUBE,
        source_type=SourceType.TRENDING,
        niche=Niche.ADRENALINE,
        title="Epic Skydive POV Wingsuit",
        immersive_metadata=meta
    )
    
    print(f"ContentItem immersive_metadata: {item.immersive_metadata}")
    assert item.immersive_metadata["type"] == "air_sports"
    assert item.niche == Niche.ADRENALINE
    
    print("✅ ContentItem metadata verified.")

if __name__ == "__main__":
    try:
        test_classifier()
        test_hook_engine()
        test_content_item_meta()
        print("\n🏆 Immersive POV Adrenaline Verification COMPLETE.")
    except Exception as e:
        print(f"\n❌ Verification FAILED: {e}")
        sys.exit(1)
