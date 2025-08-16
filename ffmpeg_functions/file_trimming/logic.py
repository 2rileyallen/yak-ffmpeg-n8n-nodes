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

def run_ffmpeg_command(command):
    """Runs an FFmpeg command and handles errors."""
    is_windows = sys.platform == "win32"
    subprocess.run(command, check=True, capture_output=True, text=True, shell=is_windows)

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

    output_path = None
    output_as_file_path = True # Default
    keep_segments = params.get('keepTrimmedSegments', False)
    
    # If keeping segments, we must output to a file path.
    if keep_segments:
        output_as_file_path = True
    else:
        output_as_file_path = params.get('outputAsFilePath', True)

    try:
        input_path = get_file_path(params, 'input')
        start_time = float(params.get('startTime', 0))
        end_time = float(params.get('endTime', 10))
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

        duration = get_media_duration(input_path)
        if duration is None:
            raise ValueError("Could not determine the duration of the input file.")
        if start_time >= end_time or start_time > duration:
            raise ValueError("Start time must be less than end time and within the media's duration.")

        # --- Determine Output Path ---
        if output_as_file_path:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            _, ext = os.path.splitext(input_path)
            if not ext: ext = ".mp4"
            output_path = os.path.join(temp_dir, f"ffmpeg_trim_output{ext}")

        # --- 1. Create Main Trimmed Segment ---
        main_command = [
            'ffmpeg', '-y', '-i', input_path,
            '-ss', str(start_time),
            '-to', str(end_time),
            '-c', 'copy', # Use stream copy for speed, as no re-encoding is needed
            output_path
        ]
        run_ffmpeg_command(main_command)

        json_response = {}

        # --- 2. Create "Before" and "After" Segments if Requested ---
        if keep_segments:
            path_parts = os.path.splitext(output_path)
            
            # Create "before" segment if start_time > 0
            if start_time > 0:
                before_path = f"{path_parts[0]}_before{path_parts[1]}"
                before_command = [
                    'ffmpeg', '-y', '-i', input_path,
                    '-to', str(start_time),
                    '-c', 'copy',
                    before_path
                ]
                run_ffmpeg_command(before_command)
                json_response['before_segment_path'] = before_path

            # Create "after" segment if end_time < duration
            if end_time < duration:
                after_path = f"{path_parts[0]}_after{path_parts[1]}"
                after_command = [
                    'ffmpeg', '-y', '-i', input_path,
                    '-ss', str(end_time),
                    '-c', 'copy',
                    after_path
                ]
                run_ffmpeg_command(after_command)
                json_response['after_segment_path'] = after_path

        # --- Handle Final Output ---
        if not output_as_file_path:
            with open(output_path, 'rb') as f:
                binary_data = f.read()
            encoded_data = base64.b64encode(binary_data).decode('utf-8')
            json_response['binary_data'] = encoded_data
            json_response['file_name'] = os.path.basename(output_path)
        else:
            json_response['output_path'] = output_path
        
        print(json.dumps(json_response))

    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        error_message = f"FFmpeg command failed. Stderr: {e.stderr}" if hasattr(e, 'stderr') else str(e)
        print(json.dumps({"error": error_message}))
        sys.exit(1)
    finally:
        # Clean up the primary temp file if binary output was used
        if not output_as_file_path and output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                sys.stderr.write(f"Error cleaning up temporary file {output_path}: {e}\n")

if __name__ == '__main__':
    main()
