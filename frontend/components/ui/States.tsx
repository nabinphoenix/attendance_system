import { Button } from "./Button";
import { SystemFeedback } from "./SystemFeedback";

export function EmptyState({title,description,action}:{title:string;description?:string;action?:React.ReactNode}){return <div className="grid min-h-36 place-items-center p-6 text-center"><div><p className="app-title font-medium">{title}</p>{description&&<p className="app-caption mt-1 text-sm">{description}</p>}{action&&<div className="mt-4">{action}</div>}</div></div>}
export function ErrorState({title="Unable to load this page",description,onRetry}:{title?:string;description?:string;onRetry?:()=>void}){return <SystemFeedback tone="danger" title={title} description={description} action={onRetry && <Button size="sm" variant="danger" onClick={onRetry}>Try again</Button>} />}
export function LoadingState({label="Loading"}:{label?:string}){return <div role="status" className="space-y-3 py-2"><span className="sr-only">{label}</span>{[1,2,3].map(item=><div key={item} className="h-14 animate-pulse rounded-lg bg-slate-800/70"/>)}</div>}
