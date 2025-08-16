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
        out_w = int(params.get('outputWidth', 1920))
        out_h = int(params.get('outputHeight', 1080))
        method = params.get('resizeMethod', 'stretch')
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

        video_filter = ""
        # --- Build Filter Based on Method ---
        if method == 'stretch':
            video_filter = f"scale={out_w}:{out_h}"
        
        elif method == 'crop':
            anchor = params.get('cropAnchor', 'center')
            # Scale to cover the area, then crop the excess.
            # SAR=1 ensures pixels are square before calculations.
            scale_filter = f"scale='max({out_w}/iw,{out_h}/ih)*iw':'max({out_w}/iw,{out_h}/ih)*ih',setsar=1"
            
            x, y = '0', '0'
            if 'left' in anchor.lower(): x = '0'
            elif 'right' in anchor.lower(): x = '(iw-ow)'
            else: x = '(iw-ow)/2' # Center
            
            if 'top' in anchor.lower(): y = '0'
            elif 'bottom' in anchor.lower(): y = '(ih-oh)'
            else: y = '(ih-oh)/2' # Center

            crop_filter = f"crop={out_w}:{out_h}:{x}:{y}"
            video_filter = f"{scale_filter},{crop_filter}"

        elif method == 'pad':
            anchor = params.get('placementAnchor', 'center')
            color = params.get('padColor', 'black')
            # Scale to fit inside the area, then pad the rest.
            scale_filter = f"scale='min({out_w}/iw,{out_h}/ih)*iw':'min({out_w}/iw,{out_h}/ih)*ih'"
            
            x, y = '0', '0'
            if 'left' in anchor.lower(): x = '0'
            elif 'right' in anchor.lower(): x = f"({out_w}-iw)"
            else: x = f"({out_w}-iw)/2" # Center
            
            if 'top' in anchor.lower(): y = '0'
            elif 'bottom' in anchor.lower(): y = f"({out_h}-ih)"
            else: y = f"({out_h}-ih)/2" # Center

            pad_filter = f"pad={out_w}:{out_h}:{x}:{y}:color={color}"
            video_filter = f"{scale_filter},{pad_filter}"

        # --- Determine Output Path and Execute ---
        output_as_file_path = params.get('outputAsFilePath', True)
        output_path = None
        
        if output_as_file_path:
            output_path = params.get('outputFilePath')
            if not output_path: raise ValueError("Output file path is required.")
        else:
            temp_dir = tempfile.gettempdir()
            _, ext = os.path.splitext(input_path)
            # Default to a transparency-supporting format if needed
            if method == 'pad' and color == 'transparent': ext = ".mov"
            elif not ext: ext = ".mp4"
            output_path = os.path.join(temp_dir, f"ffmpeg_resize_output{ext}")

        command = ['ffmpeg', '-y', '-i', input_path, '-vf', video_filter]
        
        # Handle transparency
        if method == 'pad' and color == 'transparent':
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
