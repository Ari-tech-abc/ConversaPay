const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
for(const file of fs.readdirSync(__dirname).filter(name=>/^test_.*\.cjs$/.test(name)).sort()){
 console.log('TEST '+file);
 const result=spawnSync(process.execPath,[path.join(__dirname,file)],{stdio:'inherit',env:process.env});
 if(result.status!==0)process.exit(result.status||1);
}
