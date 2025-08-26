import logging

points = {
    "REDDIT":15,
    "STEAM":10,
    "UBER":15,
    "LINKEDIN":25,
    "TWITCH":10,
    "AMAZON_PRIME":25,
    "NETFLIX":25,
    "ZOMATO":15,
    "SPOTIFY":15,
    "GITHUB": 10,
    "TWITTER":10,
}

def calculate_max_points(points_dict):
    return sum(points_dict.values())

def get_dynamic_task_score(uniqueness_count, task_type):
    max_point = points[task_type]

    if uniqueness_count >= 10:
        return max_point
    elif 5 <= uniqueness_count <= 9:
        return max_point * 0.5
    elif 1 <= uniqueness_count <= 4:
        return max_point * 0.1
    else:
        return 0

def calculate_quality_n_type_score(input_data, config, unique_entry_details):
    """Calculate quality score based on contribution data and input files."""
    type_scores = {}
    total_secured_points = 0
    total_max_score = 0

    # Convert unique_entry_details into a dictionary for quick lookup
    logging.info(f"unique_entry_details is {unique_entry_details}")
    unique_entries_dict = {
    entry["type"]: {
        "unique_entry_count": entry["unique_entry_count"], 
        "type_unique_score": entry["type_unique_score"]
    }
        for entry in unique_entry_details
    }
    # Loop through each contribution in the input data
    for contribution in input_data['contributions']:
        task_type = contribution['type']
        securedSharedData = contribution['securedSharedData']
        type_unique_count = unique_entries_dict.get(task_type)["unique_entry_count"] # Get unique entries if available
        type_uniqueness_score = unique_entries_dict.get(task_type)["type_unique_score"] 

        if task_type in points:
            total_max_score += points[task_type] # Only sum max scores for submitted types
        
        if task_type in ['UBER', 'AMAZON_PRIME', 'ZOMATO', 'SPOTIFY', 'NETFLIX']:
            type_points = get_dynamic_task_score(type_unique_count, task_type)  # Use unique_entries instead of order_count
            type_quality_score = type_points / points[task_type] if points[task_type] > 0 else 0
        elif task_type in ['REDDIT', 'STEAM', 'TWITCH', 'TWITTER', 'LINKEDIN', 'GITHUB']:
            type_points = points[task_type] * type_uniqueness_score
            type_quality_score = type_points / points[task_type] if points[task_type] > 0 else 0
        else:
            type_points = 0  # Default type_points for unknown types
            type_quality_score = 0

        type_scores[task_type] = {
            "type_points": type_points,
            "type_uniqueness_score": type_uniqueness_score,
            "type_quality_score": type_quality_score
        }
        total_secured_points += type_points

    # Normalize the total score
    normalized_total_score = total_secured_points / total_max_score if total_max_score > 0 else 0

    # Log the results
    logging.info(f"Final Scores: {type_scores}")
    logging.info(f"Total Secured Score: {total_secured_points}")
    logging.info(f"Total Max Score: {total_max_score}")
    logging.info(f"Normalized Total Score: {normalized_total_score}")

    return {"quality_score" : normalized_total_score, "type_scores": type_scores}