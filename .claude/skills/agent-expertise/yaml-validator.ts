#!/usr/bin/env bun

import * as fs from 'fs';
import * as path from 'path';
import yaml from 'js-yaml';

interface ValidationResult {
    file: string;
    valid: boolean;
    errors?: string[];
}

function findYamlFiles(dir: string): string[] {
    const files: string[] = [];

    try {
        const entries = fs.readdirSync(dir, {withFileTypes: true});

        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);

            if (entry.isDirectory()) {
                files.push(...findYamlFiles(fullPath));
            } else if (
                entry.isFile() &&
                (entry.name.endsWith('.yaml') || entry.name.endsWith('.yml'))
            ) {
                files.push(fullPath);
            }
        }
    } catch (error) {
        console.error(`Error reading directory ${dir}:`, error);
    }

    return files;
}

function validateYamlFile(filePath: string): ValidationResult {
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        yaml.load(content, {filename: filePath});
        return {file: filePath, valid: true};
    } catch (error) {
        return {
            file: filePath,
            valid: false,
            errors: [error instanceof Error ? error.message : String(error)],
        };
    }
}

function main() {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        console.error('Usage: yaml-validator <folder-path>');
        console.error('Example: yaml-validator ./.claude/skills');
        process.exit(1);
    }

    const folderPath = args[0];

    if (!fs.existsSync(folderPath)) {
        console.error(`Error: Folder '${folderPath}' does not exist`);
        process.exit(1);
    }

    if (!fs.statSync(folderPath).isDirectory()) {
        console.error(`Error: '${folderPath}' is not a directory`);
        process.exit(1);
    }

    console.log(`Searching for YAML files in: ${folderPath}\n`);

    const yamlFiles = findYamlFiles(folderPath);

    if (yamlFiles.length === 0) {
        console.log('No YAML files found.');
        process.exit(0);
    }

    console.log(`Found ${yamlFiles.length} YAML file(s)\n`);

    const results: ValidationResult[] = [];
    let hasErrors = false;

    for (const file of yamlFiles) {
        const result = validateYamlFile(file);
        results.push(result);

        if (!result.valid) {
            hasErrors = true;
            console.error(`✗ ${file}`);
            if (result.errors) {
                result.errors.forEach((err) => console.error(`  - ${err}`));
            }
            console.error('');
        } else {
            console.log(`✓ ${file}`);
        }
    }

    console.log('\n' + '='.repeat(50));
    console.log(
        `Summary: ${results.filter((r) => r.valid).length}/${results.length} files valid`
    );

    if (hasErrors) {
        console.error('\nValidation failed with errors.');
        process.exit(1);
    } else {
        console.log('\nAll YAML files are valid! ✓');
        process.exit(0);
    }
}

main();
