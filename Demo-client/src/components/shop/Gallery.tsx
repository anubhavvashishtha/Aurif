import { useState } from 'react';
import { X, ZoomIn } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { type GalleryImage } from '@/lib/catalog';
export function Gallery({images,name}:{images:GalleryImage[];name:string}) {
 const [active,setActive]=useState(0);const [zoom,setZoom]=useState(false);const image=images[active];
 return <div><div className="relative overflow-hidden rounded-md bg-muted"><img src={image?.src} alt={image?.alt??name} className={`aspect-square w-full object-cover ${image?.zoom?'scale-125':''}`}/><Button variant="hero" size="icon" aria-label="Enlarge photo" onClick={()=>setZoom(true)} className="absolute bottom-4 right-4"><ZoomIn/></Button></div><div className="mt-3 flex gap-3">{images.map((im,i)=><Button key={i} variant="outline" onClick={()=>setActive(i)} aria-label={`Photo ${i+1}`} aria-pressed={active===i} className={`h-20 w-20 overflow-hidden p-0 ${active===i?'ring-2 ring-ring':''}`}><img src={im.src} alt={im.alt} className={`h-full w-full object-cover ${im.zoom?'scale-125':''}`}/></Button>)}</div>{zoom&&<div role="dialog" aria-modal="true" aria-label="Product photo" className="fixed inset-0 z-50 flex items-center justify-center bg-ink/95 p-6" onClick={()=>setZoom(false)}><Button autoFocus variant="hero" size="icon" aria-label="Close photo" className="absolute right-6 top-6" onClick={()=>setZoom(false)}><X/></Button><img src={image?.src} alt={image?.alt} className="max-h-[85vh] max-w-full object-contain"/></div>}</div>
}
