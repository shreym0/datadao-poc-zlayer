import hashlib
import zipfile
import redis
import hashlib
import json
import logging
import os
from urllib.parse import urlparse
import requests
import gnupg
from jwt import encode as jwt_encode
from datetime import datetime, timedelta, timezone

# Connect to Redis
def get_redis_client():
    try:
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        redis_port = int(os.environ.get('REDIS_PORT', 6379))
        redis_username = os.environ.get('REDIS_USERNAME', '')
        redis_password = os.environ.get('REDIS_PWD', 'password')
        
        redis_client = redis.StrictRedis(
            host=redis_host,
            port=redis_port,
            username=redis_username,
            password=redis_password,
            ssl=True,
            decode_responses=True,
            socket_timeout=30,
            retry_on_timeout=True
        )

        redis_client.ping()
        return redis_client
    except redis.ConnectionError:
        logging.warning("Redis connection failed. Proceeding without caching.")
        return None

def hash_value(value):
    return hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) else hash_value(json.dumps(value))

# To extract type and securedSharedData from the contribution field of dataset shared
# This data will be used for hashing as well as caching in Redis
def process_secured_data(contributions):
    processed = []
    for entry in contributions:
        type = entry.get("type")
        secured_data = entry.get("securedSharedData")
        
        hashed_data = {
            key: (
                {k: hash_value(v) for k, v in value.items()} if isinstance(value, dict) else
                [hash_value(item) for item in value] if isinstance(value, list) else
                hash_value(value)
            )
            for key, value in secured_data.items()
        }

        processed.append({"type": type, "securedSharedData": hashed_data})
    return processed


def compare_secured_data(processed_curr_data: list, processed_old_data: list):
    result = []
    total_score = 0  # To calculate total normalized score

    # Convert processed_curr_data to a dictionary for easier lookup
    curr_dict = {item["type"]: item["securedSharedData"] for item in processed_curr_data}
    old_dict = {item["type"]: item["securedSharedData"] for item in processed_old_data}
    logging.info(f"curr_dict {curr_dict}, old_dict {old_dict}")

    # Process all types from curr_dict
    for type, curr_secured_data in curr_dict.items():
        unique_hashes = set()
        total_hashes = set()
        old_secured_data = old_dict.get(type, {})  # Get old data if available

        logging.info(f"Processing types: {type}, curr_secured_data: {curr_secured_data}")

        # If type is not in old_dict, consider all hashes unique
        if type not in old_dict:
            for key, value in curr_secured_data.items():
                if isinstance(value, dict):
                    unique_hashes.update(value.values())
                    total_hashes.update(value.values())

                elif isinstance(value, list):
                    unique_hashes.update(value)
                    total_hashes.update(value)

                elif isinstance(value, str):
                    unique_hashes.add(str(value))
                    total_hashes.add(str(value))

            type_unique_score = 1.0  # Fully unique
        else:
            # Compare fields inside securedSharedData
            for key, old_value in old_secured_data.items():
                curr_value = curr_secured_data.get(key, {})

                # Convert dict values to sets of hashes
                if isinstance(old_value, dict):
                    old_hashes = set(old_value.values())
                    curr_hashes = set(curr_value.values()) if isinstance(curr_value, dict) else set()

                # Convert list values to sets of hashes
                elif isinstance(old_value, list):
                    old_hashes = set(old_value)
                    curr_hashes = set(curr_value) if isinstance(curr_value, list) else set()

                # Fix: Handle string values (hash comparison)
                elif isinstance(old_value, str):
                    old_hashes = {old_value}
                    curr_hashes = {curr_value} if isinstance(curr_value, str) else set()

                unique_hashes.update(curr_hashes - old_hashes)
                total_hashes.update(curr_hashes)

            # Calculate type unique score (avoid division by zero)
            type_unique_score = (len(unique_hashes) / len(total_hashes)) if total_hashes else 0

        total_score += type_unique_score  # Sum up scores

        # Add results
        result.append({
            "type": type,
            "unique_hashes_in_curr": len(unique_hashes),
            "total_hashes_in_curr": len(total_hashes),
            "type_unique_score": type_unique_score
        })

    # Calculate total normalized score
    total_normalized_score = total_score / len(result) if result else 0
    logging.info(f"Final Result, normalized score: {total_normalized_score}")

    return {
        "comparison_results": result,
        "total_normalized_score": total_normalized_score
    }

def get_unique_entries(comparison_results):
    """
    Extracts type and unique entry count from comparison results.

    :param comparison_results: List of dictionaries containing comparison results
    :return: List of dictionaries with type and unique entry count
    """
    return [
        {
            "type": entry["type"],
            "unique_entry_count": entry["unique_hashes_in_curr"],
            "type_unique_score": entry["type_unique_score"]
        }
        for entry in comparison_results
    ]

def download_file(file_url, save_path):
    response = requests.get(file_url, stream=True)
    
    if response.status_code == 200:
        with open(save_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        return save_path  # File downloaded successfully
    
    return None  # Return None if file is not found or any other non-200 response

def download_and_decrypt(file_url, signature):
    try:
        # Ensure the download folder exists
        download_folder = "./download"
        os.makedirs(download_folder, exist_ok=True)
        
        # Define paths
        encrypted_file_path = os.path.join(download_folder, "encrypted_file.gpg")
        decrypted_file_path = os.path.join(download_folder, "decrypted.json")
        decrypted_zip_path = os.path.join(download_folder, "decrypted.zip")
        extracted_folder = os.path.join(download_folder, "extracted")

        # Initialize GPG instance
        gpg = gnupg.GPG()

        # Download the encrypted file
        result = download_file(file_url, encrypted_file_path)
        if not result:  # Skip if download failed
            return None  

        # Read encrypted content
        with open(encrypted_file_path, 'rb') as encrypted_file:
            encrypted_data = encrypted_file.read()

        # Decrypt the data
        decrypted_data = gpg.decrypt(encrypted_data, passphrase=signature)

        if not decrypted_data.ok:
            raise Exception(f"Decryption failed: {decrypted_data.stderr}")

        # Save decrypted output
        with open(decrypted_zip_path, 'wb') as decrypted_file:
            decrypted_file.write(decrypted_data.data)

        # Check if the decrypted file is a ZIP archive
        if zipfile.is_zipfile(decrypted_zip_path):
            os.makedirs(extracted_folder, exist_ok=True)

            with zipfile.ZipFile(decrypted_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_folder)
            
            # Find JSON file inside the extracted folder
            json_file = None
            for root, _, files in os.walk(extracted_folder):
                for file in files:
                    if file.endswith(".json"):
                        json_file = os.path.join(root, file)
                        break

            if json_file:
                print(f"Decryption successful, JSON extracted to {json_file}")
                return json_file
            else:
                raise Exception("No JSON file found inside the decrypted ZIP")
        else:
            # If the decrypted output is not a ZIP, assume it's JSON
            decrypted_json = json.loads(decrypted_data.data)
            with open(decrypted_file_path, 'w') as json_file:
                json.dump(decrypted_json, json_file, indent=2)

            print(f"Decryption successful, saved to {decrypted_file_path}")
            return decrypted_file_path

    except Exception as error:
        logging.warning(f"Error during decryption: {error}")
        return None


# Fetch file mappings from API
def generate_jwt_token(wallet_address: str, secret_key: str, expiration_time: int) -> str:
    """Generate a JWT token for a given wallet address."""
    exp = datetime.now(timezone.utc) + timedelta(seconds=expiration_time)

    payload = {
        'exp': exp,
        'walletAddress': wallet_address  # Send wallet address in the payload
    }
    
    # Encode the JWT
    token = jwt_encode(payload, secret_key, algorithm='HS256')
    return token

def get_file_details_from_wallet_address(wallet_address):
    """Fetch file mappings for a given wallet address with JWT authentication."""
    validator_base_api_url = os.environ.get('VALIDATOR_BASE_API_URL')
    secret_key = os.environ.get('JWT_SECRET_KEY')  # Retrieve the secret key from environment variables
    expiration_time = 600  # JWT expiration time in seconds (10 minutes)

    if not validator_base_api_url or not secret_key:
        raise ValueError("VALIDATOR_BASE_API_URL and JWT_SECRET_KEY must be set in environment variables.")

    jwt_token = generate_jwt_token(wallet_address, secret_key, expiration_time)

    endpoint = "/api/userinfo"
    url = f"{validator_base_api_url.rstrip('/')}{endpoint}"

    payload = {"walletAddress": wallet_address}  # Send walletAddress in the body
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt_token}"  # Attach JWT token
    }

    response = requests.post(url, json=payload, headers=headers)  # Make POST request

    if response.status_code == 200:
        return response.json()  # Return JSON response
    else:
        return []  # Return empty list in case of an error

def main(curr_file_id, curr_input_data, file_list):
    redis_client = get_redis_client()
    processed_curr_data = process_secured_data(curr_input_data.get("contributions", []))
    processed_old_data = []
    sign = os.environ.get("SIGNATURE")
    if redis_client:
        pipeline = redis_client.pipeline()
        for file in file_list:
            pipeline.get(file.get("fileId"))
        stored_data_list = pipeline.execute()

        for idx, stored_data in enumerate(stored_data_list):
            if stored_data:
                # If the data exists in Redis, process it
                processed_old_data.extend(json.loads(stored_data))
                
            else:
                # If data is not found in Redis, download and process the file
                file_url = file_list[idx].get("fileUrl")
                if file_url:
                    decrypted_data = download_and_decrypt(file_url, sign)
                    if not decrypted_data:  # Skip if download failed
                        logging.warning(f"Skipping file {file_url} due to download error.")
                        continue  # Move to the next file
                    logging.info(f"Download called for fileId: {file_list[idx].get('fileId')}")
                    # Load data from the downloaded JSON file
                    with open(decrypted_data, 'r', encoding="utf-8") as json_file:
                        downloaded_data = json.load(json_file)
                    # Process and append the new data
                    processed_old_data += process_secured_data(downloaded_data.get("contributions"))

        logging.info(f"Processed Redis data: {processed_old_data}")

    else:
        # If no Redis client is available, download files from the list
        for file in file_list:
            file_url = file.get("fileUrl")
            if file_url:
                decrypted_data = download_and_decrypt(file_url, sign)
                if not decrypted_data:  # Skip if download failed
                        logging.warning(f"Skipping file {file_url} due to download error.")
                        continue  # Move to the next file
                logging.info(f"Download called for file: {file_url}")
                # Load data from the decrypted JSON file
                with open(decrypted_data, 'r', encoding="utf-8") as json_file:
                    downloaded_data = json.load(json_file)
                processed_old_data += process_secured_data(downloaded_data.get("contributions"))

    # Store current data in Redis if available
    if redis_client:
        redis_client.set(curr_file_id, json.dumps(processed_curr_data))

    # Compare current and old data
    response = compare_secured_data(processed_curr_data, processed_old_data)

    # Return the processed data
    return {
        "avg_score": response["total_normalized_score"], 
        "result": response["comparison_results"] 
    }

def uniqueness_helper(curr_input_data):
    wallet_address = curr_input_data.get('walletAddress')
    file_list = get_file_details_from_wallet_address(wallet_address) 
    logging.info(f"File list: {file_list}")
    curr_file_id = os.environ.get('FILE_ID') 
    logging.info(f"Current file id: {curr_file_id}")
    response = main(curr_file_id, curr_input_data, file_list)
    res = {
        "unique_entries": get_unique_entries(response.get("result")),
        "uniqueness_score": response.get("avg_score")
    }
    return res


