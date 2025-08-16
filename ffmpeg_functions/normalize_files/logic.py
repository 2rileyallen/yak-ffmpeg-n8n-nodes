import sys
import json
import subprocess
import tempfile
import os
import base64

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
        media_type = params.get('mediaType', 'video')
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

        command = ['ffmpeg', '-y', '-i', input_path]
        output_ext = ""

        # --- VIDEO NORMALIZATION ---
        if media_type == 'video':
            video_filters = []
            resolution = params.get('videoResolution', 'original')
            aspect_ratio = params.get('videoAspectRatio', 'original')
            frame_rate = params.get('videoFrameRate', 'original')
            output_ext = params.get('videoFormat', 'mp4')

            if resolution != 'original':
                video_filters.append(f"scale={resolution}")
            if aspect_ratio != 'original':
                video_filters.append(f"setdar={aspect_ratio.replace(':', '/')}")
            
            # Default SAR normalization
            video_filters.append("setsar=1")

            if video_filters:
                command.extend(['-vf', ",".join(video_filters)])
            
            if frame_rate != 'original':
                command.extend(['-r', frame_rate])

            # Default normalizations
            command.extend(['-c:v', 'libx24', '-pix_fmt', 'yuv420p', '-c:a', 'aac'])

        # --- AUDIO NORMALIZATION ---
        elif media_type == 'audio':
            loudness = params.get('audioLoudness', '-14')
            output_ext = params.get('audioFormat', 'mp3')
            
            # EBU R128 loudness normalization filter
            audio_filter = f"loudnorm=I={loudness}:LRA=7:tp=-2"
            command.extend(['-af', audio_filter])
            
            # Default normalizations
            command.extend(['-ar', '48000'])

        # --- IMAGE NORMALIZATION ---
        elif media_type == 'image':
            output_ext = params.get('imageFormat', 'png')
            quality = params.get('imageQuality', 92)
            
            # Default sRGB conversion
            command.extend(['-vf', 'colorspace=all=srgb:iall=srgb:fast=1'])

            if output_ext in ['jpg', 'jpeg']:
                command.extend(['-q:v', str(int(31 * (100 - quality) / 99))]) # Convert 1-100 scale to ffmpeg's 2-31 scale
            elif output_ext == 'webp':
                command.extend(['-quality', str(quality)])

        # --- Determine Output Path and Execute ---
        output_as_file_path = params.get('outputAsFilePath', True)
        output_path = None
        
        if output_as_file_path:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"ffmpeg_normalized_output.{output_ext}")
        
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
        if 'output_path' in locals() and not output_as_file_path and output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                sys.stderr.write(f"Error cleaning up temporary file {output_path}: {e}\n")

if __name__ == '__main__':
    main()
