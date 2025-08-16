const path = require('path');
const { task, src, dest } = require('gulp');

task('build:icons', copyIcons);

function copyIcons() {
    // This part is correct and finds icons for your node
    const nodeSource = path.resolve('nodes', '**', '*.{png,svg}');
    const nodeDestination = path.resolve('dist', 'nodes');

    // We return this stream, and remove the part that looks for credentials
    return src(nodeSource).pipe(dest(nodeDestination));
}