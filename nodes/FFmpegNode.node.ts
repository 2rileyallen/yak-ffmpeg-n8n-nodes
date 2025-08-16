import {
    IExecuteFunctions,
    ILoadOptionsFunctions,
    INodeExecutionData,
    INodeType,
    INodeTypeDescription,
    INodePropertyOptions,
    NodeConnectionType,
    NodeOperationError,
    IDataObject,
} from 'n8n-workflow';
import { spawn } from 'child_process';
import * as path from 'path';
import { promises as fs } from 'fs';

// --- HELPER FUNCTION ---
// Moved readJson outside the class to make it a static helper.
// This solves all the "duplicate function" and "this context" errors.
async function readJson<T = any>(filePath: string): Promise<T> {
    try {
        const raw = await fs.readFile(filePath, 'utf-8');
        return JSON.parse(raw) as T;
    } catch (error) {
        // We can't use the node's logger here, so console.error is appropriate.
        console.error(`Error reading JSON file at ${filePath}:`, error);
        // Re-throw a more specific error for the node to catch.
        throw new Error(`Failed to read or parse JSON file: ${filePath}`);
    }
}


// --- INTERFACES ---
// Define the structure of a function entry in the manifest
interface IFFmpegFunction {
    name: string;
    value: string;
    uiFile: string;
    scriptFile: string;
}

// Define the structure of the manifest file
interface IManifest {
    functions: IFFmpegFunction[];
}


// --- NODE IMPLEMENTATION ---
export class FFmpegNode implements INodeType {
    description: INodeTypeDescription = {
        displayName: 'FFmpeg Node',
        name: 'ffmpegNode',
        group: ['transform'],
        version: 1,
        description: 'Executes various FFmpeg functions via Python scripts.',
        defaults: {
            name: 'FFmpeg Node',
        },
        inputs: [NodeConnectionType.Main],
        outputs: [NodeConnectionType.Main],
        properties: [
            {
                displayName: 'Function',
                name: 'selectedFunction',
                type: 'options',
                typeOptions: {
                    loadOptionsMethod: 'getFunctions',
                },
                default: '',
                description: 'Select the FFmpeg function to execute.',
                required: true,
            },
        ],
    };

    constructor() {
        this.loadAndAppendDynamicProperties().catch((error) => {
            console.error('Failed to load dynamic properties:', error);
        });
    }

    /**
     * Resolves the root directory of the n8n custom node package.
     */
    private getRepoRoot(): string {
        return path.join(__dirname, '..', '..');
    }

    methods = {
        loadOptions: {
            async getFunctions(this: ILoadOptionsFunctions): Promise<INodePropertyOptions[]> {
                try {
                    const repoRoot = path.join(__dirname, '..', '..');
                    const manifestPath = path.join(repoRoot, 'ffmpeg_node_manifest.json');

                    try {
                        await fs.access(manifestPath);
                    } catch {
                        console.warn(`Manifest file not found: ${manifestPath}`);
                        return [];
                    }

                    // Call the static helper function directly
                    const manifest = await readJson<IManifest>(manifestPath);

                    if (!manifest.functions || manifest.functions.length === 0) {
                        throw new NodeOperationError(this.getNode(), 'No functions found in manifest.');
                    }

                    // FIX: Added explicit type for 'func' to resolve implicit 'any' error.
                    return manifest.functions.map((func: IFFmpegFunction) => ({
                        name: func.name,
                        value: func.value,
                        description: `Execute the ${func.name} function`,
                    }));
                } catch (error) {
                    throw new NodeOperationError(
                        this.getNode(),
                        `Failed to load functions from manifest: ${(error as Error).message}`,
                    );
                }
            },
        },
    };

    /**
     * Loads UI definitions from all functions in the manifest and appends them
     * as dynamic node properties with appropriate display conditions.
     */
    private async loadAndAppendDynamicProperties(): Promise<void> {
        try {
            const repoRoot = this.getRepoRoot();
            const manifestPath = path.join(repoRoot, 'ffmpeg_node_manifest.json');

            try {
                await fs.access(manifestPath);
            } catch {
                console.warn(`Manifest file not found: ${manifestPath}`);
                return;
            }

            // Call the static helper function directly
            const manifest = await readJson<IManifest>(manifestPath);

            if (!manifest.functions || !Array.isArray(manifest.functions)) {
                console.warn('No functions found in manifest');
                return;
            }

            for (const func of manifest.functions) {
                if (!func.uiFile || !func.value) {
                    console.warn(`Invalid function config: ${JSON.stringify(func)}`);
                    continue;
                }

                const uiStructurePath = path.join(repoRoot, func.uiFile);

                try {
                    await fs.access(uiStructurePath);
                    // Call the static helper function directly
                    const uiConfig = await readJson<{ properties?: any[] }>(uiStructurePath);
                    const props = uiConfig?.properties || [];

                    for (const prop of props) {
                        if (!prop.name || !prop.type) {
                            console.warn(`Invalid property in ${func.uiFile}:`, prop);
                            continue;
                        }

                        const dynamicProperty = {
                            ...prop,
                            displayOptions: {
                                ...(prop.displayOptions || {}),
                                show: {
                                    ...(prop.displayOptions?.show || {}),
                                    selectedFunction: [func.value],
                                },
                            },
                        };
                        this.description.properties.push(dynamicProperty);
                    }
                } catch (error) {
                    console.error(`Failed to read UI for function '${func.name}':`, (error as Error).message);
                }
            }
        } catch (error) {
            console.error('Failed to load dynamic properties:', (error as Error).message);
        }
    }

    async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
        const items = this.getInputData();
        const returnData: INodeExecutionData[] = [];
        const repoRoot = path.join(__dirname, '..', '..');

        for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
            try {
                const selectedFunctionValue = this.getNodeParameter('selectedFunction', itemIndex) as string;

                if (!selectedFunctionValue) {
                    throw new NodeOperationError(this.getNode(), 'No function selected.');
                }

                const manifestPath = path.join(repoRoot, 'ffmpeg_node_manifest.json');

                try {
                    await fs.access(manifestPath);
                } catch {
                    throw new NodeOperationError(this.getNode(), `Manifest file not found: ${manifestPath}`);
                }

                // Call the static helper function directly
                const manifest = await readJson<IManifest>(manifestPath);

                // FIX: Added explicit type for 'f' to resolve implicit 'any' error.
                const selectedFunction = manifest.functions.find((f: IFFmpegFunction) => f.value === selectedFunctionValue);
                if (!selectedFunction) {
                    throw new NodeOperationError(this.getNode(), `Function '${selectedFunctionValue}' not found in manifest.`);
                }

                const scriptPath = path.join(repoRoot, selectedFunction.scriptFile);

                try {
                    await fs.access(scriptPath);
                } catch {
                    throw new NodeOperationError(this.getNode(), `Script file not found: ${selectedFunction.scriptFile}`);
                }

                const args: string[] = [];
                const uiStructurePath = path.join(repoRoot, selectedFunction.uiFile);

                try {
                    await fs.access(uiStructurePath);
                    // Call the static helper function directly
                    const uiConfig = await readJson<{ properties?: any[] }>(uiStructurePath);

                    if (uiConfig.properties && Array.isArray(uiConfig.properties)) {
                        for (const prop of uiConfig.properties) {
                            if (!prop.name) continue;

                            const value = this.getNodeParameter(prop.name, itemIndex, prop.default || '');

                            if (value !== undefined && value !== null && value !== '') {
                                args.push(`--${prop.name}`);
                                args.push(String(value));
                            }
                        }
                    }
                } catch (error) {
                    console.warn(`Failed to load UI config for ${selectedFunction.name}:`, (error as Error).message);
                }

                // Execute the Python script
                const scriptResult = await new Promise<string>((resolve, reject) => {
                    const pythonProcess = spawn('python3', [scriptPath, ...args], {
                        stdio: ['pipe', 'pipe', 'pipe'],
                    });

                    let stdout = '';
                    let stderr = '';

                    pythonProcess.stdout.on('data', (data: Buffer) => {
                        stdout += data.toString();
                    });

                    pythonProcess.stderr.on('data', (data: Buffer) => {
                        stderr += data.toString();
                    });

                    pythonProcess.on('close', (code: number | null) => {
                        if (code !== 0) {
                            const errorMessage = stderr || `Script exited with code ${code}`;
                            return reject(new NodeOperationError(this.getNode(), `Script failed: ${errorMessage}`));
                        }
                        resolve(stdout.trim());
                    });

                    pythonProcess.on('error', (err: Error) => {
                        reject(new NodeOperationError(this.getNode(), `Failed to start script: ${err.message}`));
                    });

                    const timeout = setTimeout(() => {
                        pythonProcess.kill();
                        reject(new NodeOperationError(this.getNode(), 'Script execution timed out'));
                    }, 30000);

                    pythonProcess.on('close', () => {
                        clearTimeout(timeout);
                    });
                });

                let jsonResult: IDataObject;
                try {
                    jsonResult = JSON.parse(scriptResult);
                } catch {
                    jsonResult = {
                        output: scriptResult,
                        parseError: true
                    };
                }

                returnData.push({
                    json: jsonResult,
                    pairedItem: { item: itemIndex },
                });

            } catch (error) {
                if (this.continueOnFail()) {
                    returnData.push({
                        json: {
                            error: (error as Error).message
                        },
                        pairedItem: { item: itemIndex }
                    });
                    continue;
                }
                throw error;
            }
        }

        return [returnData];
    }
}
