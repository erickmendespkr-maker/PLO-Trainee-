'use strict';
// Offline bridge to MIT-licensed pi-poker-eval; no live poker connection.
const fs = require('node:fs');
const {evaluate, showdown, equity} = require('pi-poker-eval');
const req = JSON.parse(fs.readFileSync(0,'utf8'));
let result;
if(req.operation === 'evaluate') result=evaluate(req.variant,req.hole,req.board);
else if(req.operation === 'showdown') result=showdown(req.variant,req.board,req.holes);
else if(req.operation === 'equity') result=equity(req.request);
else throw Error('unsupported operation');
process.stdout.write(JSON.stringify({engine:'pi-poker-eval',result})+'\n');
