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
        fade_color = params.get('fadeColor', 'black')
        fade_duration = float(params.get('fadeDuration', 1))
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

        video_duration = get_media_duration(input_path)
        if video_duration is None:
            raise ValueError("Could not determine the duration of the input video file.")

    except (ValueError, TypeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # --- Build Filter Complex ---
    video_filter = ""
    if transition_type == 'fadeIn':
        d = min(fade_duration, video_duration)
        video_filter = f"fade=t=in:st=0:d={d}:color={fade_color}"
    elif transition_type == 'fadeOut':
        d = min(fade_duration, video_duration)
        st = video_duration - d
        video_filter = f"fade=t=out:st={st}:d={d}:color={fade_color}"
    elif transition_type == 'fadeInOut':
        d = min(fade_duration, video_duration / 2)
        st_out = video_duration - d
        video_filter = f"fade=t=in:st=0:d={d}:color={fade_color},fade=t=out:st={st_out}:d={d}:color={fade_color}"
    
    # --- Determine Output Path and Execute ---
    output_as_file_path = params.get('outputAsFilePath', True)
    output_path = None
    
    try:
        if output_as_file_path:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            ext = ".mov" if fade_color == 'transparent' else ".mp4"
            output_path = os.path.join(temp_dir, f"ffmpeg_fade_output{ext}")

        command = ['ffmpeg', '-y', '-i', input_path, '-vf', video_filter]
        
        # Handle transparency
        if fade_color == 'transparent':
            command.extend(['-c:v', 'prores_ks', '-pix_fmt', 'yuva444p10le'])
        else:
            command.extend(['-c:v', 'libx264', '-pix_fmt', 'yuv420p'])

        command.extend(['-c:a', 'copy', output_path])

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
        if not output_as_file_path and 'output_path' in locals() and output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                sys.stderr.write(f"Error cleaning up temporary file {output_path}: {e}\n")

if __name__ == '__main__':
    main()
