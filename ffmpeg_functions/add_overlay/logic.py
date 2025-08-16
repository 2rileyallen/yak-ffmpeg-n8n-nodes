import sys
import json
import subprocess
import tempfile
import os
import base64

def get_media_info(file_path):
    """Gets media information like duration and stream types using ffprobe."""
    command = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', file_path
    ]
    try:
        is_windows = sys.platform == "win32"
        result = subprocess.run(command, capture_output=True, text=True, check=True, shell=is_windows)
        info = json.loads(result.stdout)
        
        duration = float(info.get('format', {}).get('duration', 0))
        has_video = any(s['codec_type'] == 'video' for s in info.get('streams', []))
        has_audio = any(s['codec_type'] == 'audio' for s in info.get('streams', []))
        is_image = has_video and duration < 0.1

        return {'duration': duration, 'has_video': has_video, 'has_audio': has_audio, 'is_image': is_image}
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
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

    layers = []
    # --- 1. Dynamically Parse Layers ---
    for i in range(1, 11): # Loop from layer 1 to 10
        is_binary_key = f"layer{i}IsBinary"
        binary_prop_key = f"layer{i}BinaryPropertyName"
        file_path_key = f"layer{i}FilePath"
        
        path = None
        if params.get(is_binary_key):
            path = params.get(binary_prop_key)
        else:
            path = params.get(file_path_key)

        # If a path exists for this layer, process it. Otherwise, skip.
        if path and os.path.exists(path):
            info = get_media_info(path)
            if info:
                layers.append({
                    'path': path,
                    'info': info,
                    'loop': params.get(f"layer{i}Loop", False),
                    'trim_to_this': params.get(f"layer{i}TrimToThis", False)
                })

    if not layers:
        print(json.dumps({"error": "No valid media layers provided."}))
        sys.exit(1)

    # --- 2. Determine Final Duration ---
    final_duration = 0
    trim_master_layer = next((layer for layer in layers if layer['trim_to_this']), None)

    if trim_master_layer:
        final_duration = trim_master_layer['info']['duration']
    else:
        # Find the longest duration among non-looped, non-image files
        for layer in layers:
            if not layer['loop'] and not layer['info']['is_image']:
                final_duration = max(final_duration, layer['info']['duration'])
    
    if final_duration == 0:
        final_duration = 10 # Default for image-only or indeterminate compositions

    # --- 3. Build FFmpeg Command Inputs ---
    inputs = []
    video_streams, audio_streams = [], []
    for i, layer in enumerate(layers):
        if layer['info']['is_image'] or (layer['loop'] and layer is not trim_master_layer):
            inputs.extend(['-loop', '1'])
        inputs.extend(['-i', layer['path']])
        
        if layer['info']['has_video']: video_streams.append(f"[{i}:v]")
        if layer['info']['has_audio']: audio_streams.append(f"[{i}:a]")

    # --- 4. Build Filter Complex ---
    filter_complex = ""
    final_video_map, final_audio_map = None, None

    if len(video_streams) > 1:
        last_video_out = video_streams[0]
        for i in range(1, len(video_streams)):
            next_out = f"v{i}" if i < len(video_streams) else "vout"
            filter_complex += f"{last_video_out}{video_streams[i]}overlay[ {next_out}];"
            last_video_out = f"[{next_out}]"
        final_video_map = "[vout]"
    elif len(video_streams) == 1:
        filter_complex += f"{video_streams[0]}copy[vout];"
        final_video_map = "[vout]"

    if len(audio_streams) > 1:
        amix_inputs = "".join(audio_streams)
        filter_complex += f"{amix_inputs}amix=inputs={len(audio_streams)}:duration=longest[aout]"
        final_audio_map = "[aout]"
    elif len(audio_streams) == 1:
        filter_complex += f"{audio_streams[0]}acopy[aout];"
        final_audio_map = "[aout]"

    # --- 5. Determine Output Path and Execute ---
    output_as_binary = params.get('outputAsBinary', True)
    output_path = None
    
    try:
        if not output_as_binary:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            ext = ".mp4" if final_video_map else ".mp3"
            output_path = os.path.join(temp_dir, f"ffmpeg_multilayer_output{ext}")

        command = ['ffmpeg', '-y'] + inputs
        if filter_complex: command.extend(['-filter_complex', filter_complex])
        if final_video_map: command.extend(['-map', final_video_map])
        if final_audio_map: command.extend(['-map', final_audio_map])
        command.extend(['-t', str(final_duration)])
        if final_video_map: command.extend(['-c:v', 'libx264', '-pix_fmt', 'yuv420p'])
        if final_audio_map: command.extend(['-c:a', 'aac'])
        command.append(output_path)

        is_windows = sys.platform == "win32"
        subprocess.run(command, check=True, capture_output=True, text=True, shell=is_windows)
        
        if output_as_binary:
            with open(output_path, 'rb') as f:
                binary_data = f.read()
            encoded_data = base64.b64encode(binary_data).decode('utf-8')
            print(json.dumps({"binary_data": encoded_data, "file_name": os.path.basename(output_path)}))
        else:
             print(json.dumps({"output_path": output_path, "duration": final_duration}))

    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        error_message = f"FFmpeg command failed. Stderr: {e.stderr}" if hasattr(e, 'stderr') else str(e)
        print(json.dumps({"error": error_message, "command": " ".join(command if 'command' in locals() else [])}))
        sys.exit(1)
    finally:
        if output_as_binary and output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                sys.stderr.write(f"Error cleaning up temporary file {output_path}: {e}\n")

if __name__ == '__main__':
    main()
