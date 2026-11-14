export default class jsPDF {
  constructor(){ this.lines=[]; }
  text(t,x,y){ this.lines.push(t); }
  save(name){
    const blob=new Blob([this.lines.join("\n")], {type:"text/plain"});
    const a=document.createElement("a");
    a.href=URL.createObjectURL(blob);
    a.download=name.replace(".pdf",".txt");
    a.click();
    setTimeout(()=>URL.revokeObjectURL(a.href), 1000);
  }
}