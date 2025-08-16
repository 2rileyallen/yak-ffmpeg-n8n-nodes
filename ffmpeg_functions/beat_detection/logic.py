import sys
import json
import os
import librosa
import numpy as np

def get_file_path(params, base_name):
    """Extracts the file path from the parameters."""
    if params.get(f"{base_name}UseFilePath"):
        path = params.get(f"{base_name}FilePath")
        if not path: raise ValueError(f"File path for '{base_name}' is missing.")
        return path
    else:
        path = params.get(f"{base_name}BinaryPropertyName")
        if not path: raise ValueError(f"Binary property name for '{base_name}' is missing.")
        return path

def moving_average(data, window_size):
    """Applies a simple moving average for smoothing."""
    if window_size <= 1:
        return data
    # Pad the data to handle edges
    padded_data = np.pad(data, (window_size//2, window_size-1-window_size//2), mode='edge')
    return np.convolve(padded_data, np.ones(window_size)/window_size, mode='valid')

def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Expected a single argument: the path to the parameters JSON file."}))
        sys.exit(1)
    
    params_path = sys.argv[1]
    try:
        with open(params_path, 'r') as f:
            params = json.load(f)
    except Exception as e:
        print(json.dumps({"error": f"Failed to read or parse parameters file: {e}"}))
        sys.exit(1)

    try:
        input_path = get_file_path(params, 'input')
        beats_per_second = int(params.get('beatsPerSecond', 2))
        smoothing_factor = float(params.get('smoothingFactor', 0.5))
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

    except (ValueError, TypeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    try:
        # --- 1. Load Audio File ---
        y, sr = librosa.load(input_path)

        # --- 2. Get Onset Strength ---
        # This gives us a measure of "energy" over time
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        
        # --- 3. Sample the Strength at Regular Intervals ---
        # Calculate how many frames correspond to the desired beats per second
        hop_length = 512 # Default hop_length for onset_strength
        frames_per_sample = int((sr / hop_length) / beats_per_second)
        
        if frames_per_sample == 0:
            frames_per_sample = 1 # Avoid division by zero for high BPS

        sampled_strengths = onset_env[::frames_per_sample]
        
        # --- 4. Normalize and Smooth ---
        # Normalize strength to a 0-100 scale
        if np.max(sampled_strengths) > 0:
            normalized_strengths = (sampled_strengths / np.max(sampled_strengths)) * 100
        else:
            normalized_strengths = sampled_strengths # Avoid division by zero if silent

        # Apply smoothing based on the factor
        # A factor of 1 corresponds to a window size of roughly 1/4 of a second
        max_window_size = sr // hop_length // 4
        window_size = int(1 + (smoothing_factor * (max_window_size - 1)))
        
        smoothed_strengths = moving_average(normalized_strengths, window_size)

        # --- 5. Create Timestamped Output ---
        beat_data = []
        duration_per_sample = frames_per_sample * (hop_length / sr)
        
        for i, strength in enumerate(smoothed_strengths):
            timestamp = i * duration_per_sample
            beat_data.append({
                "timestamp": round(timestamp, 4),
                "strength": int(round(strength))
            })
            
        print(json.dumps(beat_data))

    except Exception as e:
        print(json.dumps({"error": f"An error occurred during beat detection: {str(e)}"}))
        sys.exit(1)


if __name__ == '__main__':
    main()
