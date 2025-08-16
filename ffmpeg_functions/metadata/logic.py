import sys
import json
import subprocess
import tempfile
import os
import shutil

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
        mode = params.get('mode', 'show')
        input_path = get_file_path(params, 'input')
        
        if not os.path.exists(input_path):
            raise ValueError(f"Input file not found at path: {input_path}")

        # --- MODE: Show Metadata ---
        if mode == 'show':
            command = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', input_path
            ]
            is_windows = sys.platform == "win32"
            result = subprocess.run(command, capture_output=True, text=True, check=True, shell=is_windows)
            metadata = json.loads(result.stdout)
            print(json.dumps(metadata))
            sys.exit(0)

        # --- MODE: Edit Metadata ---
        elif mode == 'edit':
            media_type = params.get('mediaType', 'video')
            metadata_args = []
            
            # Gather metadata tags based on media type
            prefix = media_type
            tags_to_check = ['Title', 'Artist', 'Album', 'Genre', 'Track', 'Author', 'Copyright', 'Comment', 'Year', 'Description']
            for tag in tags_to_check:
                param_key = f"{prefix}{tag}"
                if param_key in params and params[param_key]:
                    # FFmpeg metadata keys are often lowercase
                    metadata_args.extend([f'-metadata', f'{tag.lower()}={params[param_key]}'])

            if not metadata_args:
                raise ValueError("No metadata values were provided to edit.")

            replace_original = params.get('replaceOriginal', False)
            output_path = None
            temp_output_path = None

            # Determine the final and temporary output paths
            if replace_original:
                temp_dir = tempfile.gettempdir()
                _, ext = os.path.splitext(input_path)
                temp_output_path = os.path.join(temp_dir, f"metadata_temp_{os.path.basename(input_path)}{ext}")
                output_path = input_path # The final destination is the original path
            else:
                output_path = params.get('outputFilePath')
                if not output_path: raise ValueError("Output file path is required when not replacing original.")
                temp_output_path = output_path
            
            # FFmpeg command to copy streams and add metadata
            command = [
                'ffmpeg', '-y', '-i', input_path,
                '-c', 'copy', # Copy all streams without re-encoding
            ] + metadata_args + [temp_output_path]

            is_windows = sys.platform == "win32"
            subprocess.run(command, check=True, capture_output=True, text=True, shell=is_windows)
            
            # If replacing, perform the safe move/delete operation
            if replace_original:
                shutil.move(temp_output_path, output_path)

            print(json.dumps({"status": "Metadata edited successfully.", "output_path": output_path}))

    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        error_message = f"Operation failed. Stderr: {e.stderr}" if hasattr(e, 'stderr') else str(e)
        print(json.dumps({"error": error_message}))
        sys.exit(1)

if __name__ == '__main__':
    main()
