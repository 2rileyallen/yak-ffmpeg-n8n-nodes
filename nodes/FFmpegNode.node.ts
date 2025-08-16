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
import * as os from 'os'; // Needed for temporary directory

// --- HELPER FUNCTION ---
async function readJson<T = any>(filePath: string): Promise<T> {
    try {
        const raw = await fs.readFile(filePath, 'utf-8');
        return JSON.parse(raw) as T;
    } catch (error) {
        console.error(`Error reading JSON file at ${filePath}:`, error);
        throw new Error(`Failed to read or parse JSON file: ${filePath}`);
    }
}

// --- INTERFACES ---
interface IFFmpegFunction {
    name: string;
    value: string;
    uiFile: string;
    scriptFile: string;
}

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

                    const manifest = await readJson<IManifest>(manifestPath);

                    if (!manifest.functions || manifest.functions.length === 0) {
                        throw new NodeOperationError(this.getNode(), 'No functions found in manifest.');
                    }

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
            console.error('Failed to load dynamic properties:', error as Error);
        }
    }

    async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
        const items = this.getInputData();
        const returnData: INodeExecutionData[] = [];
        const repoRoot = path.join(__dirname, '..', '..');
        let tempFiles: string[] = [];

        for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
            try {
                const selectedFunctionValue = this.getNodeParameter('selectedFunction', itemIndex, '') as string;
                if (!selectedFunctionValue) throw new NodeOperationError(this.getNode(), 'No function selected.');

                const manifestPath = path.join(repoRoot, 'ffmpeg_node_manifest.json');
                const manifest = await readJson<IManifest>(manifestPath);
                const selectedFunction = manifest.functions.find((f: IFFmpegFunction) => f.value === selectedFunctionValue);
                if (!selectedFunction) throw new NodeOperationError(this.getNode(), `Function '${selectedFunctionValue}' not found.`);

                const scriptPath = path.join(repoRoot, selectedFunction.scriptFile);
                const uiStructurePath = path.join(repoRoot, selectedFunction.uiFile);
                await fs.access(scriptPath);

                const parameters: IDataObject = {};
                const uiConfig = await readJson<{ properties?: { name: string, type: string }[] }>(uiStructurePath);

                if (uiConfig.properties && Array.isArray(uiConfig.properties)) {
                    for (const prop of uiConfig.properties) {
                        if (!prop.name) continue;
                        try {
                            parameters[prop.name] = this.getNodeParameter(prop.name, itemIndex);
                        } catch (error) {
                            continue;
                        }
                    }
                }

                // **BINARY INPUT HANDLING**
                // This logic is generic because it relies on a naming convention
                // that all function UIs must follow for binary inputs.
                const processedParameters = { ...parameters }; // Create a copy to modify

                // Find all boolean toggles for binary data
                const binaryToggleKeys = Object.keys(processedParameters).filter(k => k.endsWith('IsBinary'));

                for (const toggleKey of binaryToggleKeys) {
                    if (processedParameters[toggleKey] === true) {
                        // If the toggle is on, find the corresponding property name field
                        const prefix = toggleKey.replace('IsBinary', '');
                        const binaryPropNameKey = `${prefix}BinaryPropertyName`;

                        if (processedParameters[binaryPropNameKey]) {
                            const binaryPropertyName = processedParameters[binaryPropNameKey] as string;
                            
                            // **THE FIX**
                            // Correctly access the data for the current item from the 'items' array.
                            const inputData = items[itemIndex];
                            const binaryInfo = inputData.binary?.[binaryPropertyName];

                            if (!binaryInfo) {
                                throw new NodeOperationError(this.getNode(), `Binary property '${binaryPropertyName}' not found in input data.`);
                            }
                            
                            const binaryBuffer = await this.helpers.getBinaryDataBuffer(itemIndex, binaryPropertyName);
                            const fileName = binaryInfo.fileName ?? `${binaryPropertyName}.bin`;

                            const tempPath = path.join(os.tmpdir(), `n8n-ffmpeg-bin-${Date.now()}-${fileName}`);
                            await fs.writeFile(tempPath, binaryBuffer);
                            tempFiles.push(tempPath);

                            // Replace the property name (e.g., 'data') with the actual temp file path.
                            // The Python script will now receive the path it needs.
                            processedParameters[binaryPropNameKey] = tempPath;
                        }
                    }
                }


                const paramsPath = path.join(os.tmpdir(), `n8n-ffmpeg-params-${Date.now()}-${itemIndex}.json`);
                await fs.writeFile(paramsPath, JSON.stringify(processedParameters, null, 2));
                tempFiles.push(paramsPath);

                const scriptResult = await new Promise<string>((resolve, reject) => {
                    const pythonProcess = spawn('python', [scriptPath, paramsPath]);
                    let stdout = '';
                    let stderr = '';
                    pythonProcess.stdout.on('data', (data) => (stdout += data.toString()));
                    pythonProcess.stderr.on('data', (data) => (stderr += data.toString()));
                    pythonProcess.on('close', (code) => {
                        if (code !== 0) return reject(new NodeOperationError(this.getNode(), `Script failed: ${stderr || `Exited with code ${code}`}`));
                        resolve(stdout.trim());
                    });
                    pythonProcess.on('error', (err) => reject(new NodeOperationError(this.getNode(), `Failed to start script: ${err.message}`)));
                });

                let jsonResult: IDataObject;
                try {
                    jsonResult = JSON.parse(scriptResult);
                } catch {
                    jsonResult = { output: scriptResult, parseError: true };
                }

                // **BINARY OUTPUT HANDLING**
                if (jsonResult.binary_data && jsonResult.file_name) {
                    const binaryBuffer = Buffer.from(jsonResult.binary_data as string, 'base64');
                    const binaryData = await this.helpers.prepareBinaryData(
                        binaryBuffer,
                        jsonResult.file_name as string,
                    );
                    
                    const executionData: INodeExecutionData = {
                        json: {}, // Can add other non-binary results here if needed
                        binary: { data: binaryData },
                        pairedItem: { item: itemIndex },
                    };
                    returnData.push(executionData);

                } else {
                    // Standard non-binary output
                    returnData.push({ json: jsonResult, pairedItem: { item: itemIndex } });
                }


            } catch (error) {
                if (this.continueOnFail()) {
                    returnData.push({ json: { error: (error as Error).message }, pairedItem: { item: itemIndex } });
                    continue;
                }
                throw error;
            } finally {
                for (const filePath of tempFiles) {
                    try {
                        await fs.unlink(filePath);
                    } catch (e) {
                        console.error(`Could not clean up temp file ${filePath}:`, e);
                    }
                }
                tempFiles = [];
            }
        }
        return this.prepareOutputData(returnData);
    }
}
