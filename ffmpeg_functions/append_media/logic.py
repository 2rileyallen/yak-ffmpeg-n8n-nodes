import sys
import json
import subprocess
import tempfile
import os
import base64

def get_media_info(file_path):
    """Gets media information, returning None for images."""
    command = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', file_path
    ]
    try:
        is_windows = sys.platform == "win32"
        result = subprocess.run(command, capture_output=True, text=True, check=True, shell=is_windows)
        info = json.loads(result.stdout)
        
        has_video = any(s['codec_type'] == 'video' for s in info.get('streams', []))
        has_audio = any(s['codec_type'] == 'audio' for s in info.get('streams', []))
        
        # This function does not support images
        if has_video and not has_audio and float(info.get('format', {}).get('duration', 1)) < 0.1:
            return None

        return {'has_video': has_video, 'has_audio': has_audio}
    except Exception as e:
        sys.stderr.write(f"Error probing file {file_path}: {e}\n")
        return None

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
        media_files_str = params.get('mediaFilesJson')
        if not media_files_str:
            raise ValueError("The 'Media Files (JSON Array)' parameter is required.")
        
        media_list = json.loads(media_files_str)
        if not isinstance(media_list, list) or len(media_list) < 2:
            raise ValueError("The input must be a JSON array with at least two media files.")

    except (ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # --- 1. Process and Validate Media List ---
    inputs = []
    filter_complex_parts = []
    stream_counter = 0
    
    # Check if all files are of the same primary type (all video or all audio)
    first_file_info = get_media_info(media_list[0].get('path'))
    if not first_file_info:
        print(json.dumps({"error": f"Could not process the first file: {media_list[0].get('path')}"}))
        sys.exit(1)
    
    is_video_concat = first_file_info['has_video']
    is_audio_concat = first_file_info['has_audio'] and not is_video_concat

    for i, media in enumerate(media_list):
        path = media.get('path')
        if not path or not os.path.exists(path):
            print(json.dumps({"error": f"File path for item {i} is invalid or missing."}))
            sys.exit(1)
        
        info = get_media_info(path)
        if not info:
            print(json.dumps({"error": f"Could not process file (or file is an image): {path}"}))
            sys.exit(1)
        
        # Enforce consistency
        if is_video_concat and not info['has_video']:
            print(json.dumps({"error": "Cannot mix video and audio-only files in a video append."}))
            sys.exit(1)
        if is_audio_concat and not info['has_audio']:
             print(json.dumps({"error": "Cannot mix audio and video files in an audio-only append."}))
             sys.exit(1)

        inputs.extend(['-i', path])
        if is_video_concat:
            filter_complex_parts.append(f"[{i}:v:0]")
        if info['has_audio']:
            filter_complex_parts.append(f"[{i}:a:0]")
        stream_counter += 1

    # --- 2. Build Filter Complex for Concatenation ---
    # Note: This simple concat filter does not handle crossfades/overlap.
    # A more complex filter graph would be needed for that.
    filter_complex = f"{''.join(filter_complex_parts)}concat=n={stream_counter}:v={1 if is_video_concat else 0}:a={1 if is_audio_concat or is_video_concat else 0}[outv][outa]"
    
    # --- 3. Determine Output Path and Execute ---
    output_as_file_path = params.get('outputAsFilePath', True)
    output_path = None
    
    try:
        if output_as_file_path:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            ext = ".mp4" if is_video_concat else ".mp3"
            output_path = os.path.join(temp_dir, f"ffmpeg_append_output{ext}")

        command = ['ffmpeg', '-y'] + inputs
        command.extend(['-filter_complex', filter_complex])
        if is_video_concat:
            command.extend(['-map', '[outv]'])
        command.extend(['-map', '[outa]'])
        command.append(output_path)

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
