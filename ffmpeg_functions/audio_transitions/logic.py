import sys
import json
import subprocess
import tempfile
import os
import base64

def get_media_duration(file_path):
    """Get the duration of a media file using ffprobe."""
    command = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file_path
    ]
    try:
        is_windows = sys.platform == "win32"
        result = subprocess.run(command, capture_output=True, text=True, check=True, shell=is_windows)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        sys.stderr.write(f"Error getting duration for {file_path}: {e}\n")
        return None

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
        transition_type = params.get('transitionType', 'fadeIn')
        fade_duration = float(params.get('fadeDuration', 5))
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

        audio_duration = get_media_duration(input_path)
        if audio_duration is None:
            raise ValueError("Could not determine the duration of the input audio file.")

    except (ValueError, TypeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # --- Build Filter Complex ---
    filter_complex = ""
    if transition_type == 'fadeIn':
        # Ensure fade duration is not longer than the clip itself
        actual_duration = min(fade_duration, audio_duration)
        filter_complex = f"afade=t=in:ss=0:d={actual_duration}"
    elif transition_type == 'fadeOut':
        actual_duration = min(fade_duration, audio_duration)
        start_time = audio_duration - actual_duration
        filter_complex = f"afade=t=out:st={start_time}:d={actual_duration}"
    elif transition_type == 'fadeInOut':
        # Ensure the two fades don't overlap on short clips
        actual_duration = min(fade_duration, audio_duration / 2)
        fade_out_start = audio_duration - actual_duration
        filter_complex = f"afade=t=in:ss=0:d={actual_duration},afade=t=out:st={fade_out_start}:d={actual_duration}"
    
    # --- Determine Output Path and Execute ---
    output_as_file_path = params.get('outputAsFilePath', True)
    output_path = None
    
    try:
        if output_as_file_path:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            # Use the original extension if possible, otherwise default to mp3
            _, ext = os.path.splitext(input_path)
            if not ext: ext = ".mp3"
            output_path = os.path.join(temp_dir, f"ffmpeg_fade_output{ext}")

        command = [
            'ffmpeg', '-y', '-i', input_path,
            '-af', filter_complex,
            output_path
        ]

        is_windows = sys.platform == "win32"
        subprocess.run(command, check=True, capture_output=True, text=True, shell=is_windows)
        
        if not output_as_file_path:
            with open(output_path, 'rb') as f:
                binary_data = f.read()
            encoded_data = base64.b64encode(binary_data).decode('utf-8')
            print(json.dumps({"binary_data": encoded_data, "file_name": os.path.basename(output_path)}))
        else:
             print(json.dumps({"output_path": output_path}))

    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        error_message = f"FFmpeg command failed. Stderr: {e.stderr}" if hasattr(e, 'stderr') else str(e)
        print(json.dumps({"error": error_message, "command": " ".join(command if 'command' in locals() else [])}))
        sys.exit(1)
    finally:
        if not output_as_file_path and output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                sys.stderr.write(f"Error cleaning up temporary file {output_path}: {e}\n")

if __name__ == '__main__':
    main()
