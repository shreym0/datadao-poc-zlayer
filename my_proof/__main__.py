import json
import logging
import os
import sys
import traceback
import zipfile
from typing import Dict, Any
from my_proof.proof import Proof

# Default to 'production' if NODE_ENV is not set
environment = os.environ.get('NODE_ENV', 'production')

# Set the input and output directories based on the environment
INPUT_DIR = './demo/input' if environment == 'development' else '/input'
OUTPUT_DIR = './demo/output' if environment == 'development' else '/output'
SEALED_DIR = './demo/sealed' if environment == 'development' else '/sealed'

logging.basicConfig(level=logging.INFO, format='%(message)s')

def load_config() -> Dict[str, Any]:
    """Load proof configuration from environment variables."""
    config = {
        'dlp_id': os.environ.get('DLP_ID', 154),  # DLP ID defaults to 154
        'input_dir': INPUT_DIR,
        'jwt_expiration_time': int(os.environ.get('JWT_EXPIRATION_TIME', 600)),
        'validator_base_api_url': os.environ.get('VALIDATOR_BASE_API_URL', None),
        'jwt_secret_key': os.environ.get('JWT_SECRET_KEY'),
        'file_id': os.environ.get('FILE_ID'),
        'signature': os.environ.get('SIGNATURE'),
        'redis_port': os.environ.get('REDIS_PORT', None),
        'redis_host': os.environ.get('REDIS_HOST', None),
        'redis_pwd': os.environ.get('REDIS_PWD', None),
        'redis_username': os.environ.get('REDIS_USERNAME', ''),
        'use_sealing': os.path.isdir(SEALED_DIR)
    }
    logging.info(f"Using config: {json.dumps(config, indent=2)}")
    return config


def run() -> None:
    """Generate proofs for all input files."""
    config = load_config()
    input_files_exist = os.path.isdir(INPUT_DIR) and bool(os.listdir(INPUT_DIR))

    if not input_files_exist:
        raise FileNotFoundError(f"No input files found in {INPUT_DIR}")
    extract_input()

    proof = Proof(config)
    proof_response = proof.generate()

    output_path = os.path.join(OUTPUT_DIR, "results.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(proof_response, f, indent=2)
    logging.info(f"Proof generation complete: {proof_response}")


def extract_input() -> None:
    """
    If the input directory contains any zip files, extract them
    :return:
    """
    for input_filename in os.listdir(INPUT_DIR):
        input_file = os.path.join(INPUT_DIR, input_filename)

        if zipfile.is_zipfile(input_file):
            with zipfile.ZipFile(input_file, 'r') as zip_ref:
                zip_ref.extractall(INPUT_DIR)


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logging.error(f"Error during proof generation: {e}")
        traceback.print_exc()
        sys.exit(1)
