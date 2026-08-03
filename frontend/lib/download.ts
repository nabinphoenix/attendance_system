import api from "./api";
export async function downloadFile(url:string,filename:string){const response=await api.get(url,{responseType:"blob"});const href=URL.createObjectURL(response.data);const link=document.createElement("a");link.href=href;link.download=filename;link.click();URL.revokeObjectURL(href)}
