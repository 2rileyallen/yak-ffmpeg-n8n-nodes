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
        similarity = float(params.get('similarity', 0.1))
        blend = float(params.get('blend', 0.1))
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

    except (ValueError, TypeError) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # --- Build Filter ---
    # The chromakey filter format is chromakey=color:similarity:blend
    # We will key out a standard green color.
    key_color = "0x00FF00"
    chroma_filter = f"chromakey=color={key_color}:similarity={similarity}:blend={blend}"
    
    # --- Determine Output Path and Execute ---
    output_as_file_path = params.get('outputAsFilePath', True)
    output_path = None
    
    try:
        if output_as_file_path:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            # To support transparency, we should default to a capable container like .mov
            output_path = os.path.join(temp_dir, "ffmpeg_greenscreen_output.mov")

        # Command needs a codec that supports an alpha (transparency) channel.
        # prores_ks is a good choice for .mov containers.
        command = [
            'ffmpeg', '-y', '-i', input_path,
            '-vf', chroma_filter,
            '-c:v', 'prores_ks', # Codec that supports alpha channel
            '-pix_fmt', 'yuva444p10le', # Pixel format for transparency
            '-c:a', 'copy', # Copy audio without re-encoding
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
