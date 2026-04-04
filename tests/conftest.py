import sys
import os

# Add src/ so tests can import parser, features, scorer, exporter, etc.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
# Add src/data/ so tests can import fasttrack, mapping, fasttrack_dataset by bare name
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'data'))
