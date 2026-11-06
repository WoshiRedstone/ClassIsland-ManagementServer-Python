import{au as j,av as H,aw as ge,ax as z,ay as F,az as B,aA as te,aB as Z,aC as Fe,aD as ye,aE as _,aF as Se,aG as Ce,d as D,C as l,r as w,c as $,aH as re,aI as ne,a5 as nt,z as at,a6 as He,aJ as Be,aK as ot,aL as ie,aM as Ue,aN as $e,aO as Re,aP as lt,U as Q,R as b,aQ as it,V as U,T as De,aR as st,aS as ut,aT as ct,aU as Ae,aV as dt,L as ht,aW as pt,aX as ft,ah as gt,W as vt,af as Te,aY as bt,Z as mt,ad as we,ae as Pe,an as xt,aZ as Ie,ag as kt,a_ as wt,a$ as yt,al as de,B as he,b0 as St}from"./index-C6rb1iUY.js";function Ct(e,t){switch(e[0]){case"hex":return t?"#000000FF":"#000000";case"rgb":return t?"rgba(0, 0, 0, 1)":"rgb(0, 0, 0)";case"hsl":return t?"hsla(0, 0%, 0%, 1)":"hsl(0, 0%, 0%)";case"hsv":return t?"hsva(0, 0%, 0%, 1)":"hsv(0, 0%, 0%)"}return"#000000"}function se(e){return e===null?null:/^ *#/.test(e)?"hex":e.includes("rgb")?"rgb":e.includes("hsl")?"hsl":e.includes("hsv")?"hsv":null}function Ut(e){return e=Math.round(e),e>=360?359:e<0?0:e}function $t(e){return e=Math.round(e*100)/100,e>1?1:e<0?0:e}const Rt={rgb:{hex(e){return B(_(e))},hsl(e){const[t,i,n,o]=_(e);return H([...Ce(t,i,n),o])},hsv(e){const[t,i,n,o]=_(e);return Z([...Se(t,i,n),o])}},hex:{rgb(e){return z(_(e))},hsl(e){const[t,i,n,o]=_(e);return H([...Ce(t,i,n),o])},hsv(e){const[t,i,n,o]=_(e);return Z([...Se(t,i,n),o])}},hsl:{hex(e){const[t,i,n,o]=te(e);return B([...ye(t,i,n),o])},rgb(e){const[t,i,n,o]=te(e);return z([...ye(t,i,n),o])},hsv(e){const[t,i,n,o]=te(e);return Z([...Fe(t,i,n),o])}},hsv:{hex(e){const[t,i,n,o]=j(e);return B([...F(t,i,n),o])},rgb(e){const[t,i,n,o]=j(e);return z([...F(t,i,n),o])},hsl(e){const[t,i,n,o]=j(e);return H([...ge(t,i,n),o])}}};function qe(e,t,i){return i=i||se(e),i?i===t?e:Rt[i][t](e):null}const le="12px",At=12,O="6px",Vt=D({name:"AlphaSlider",props:{clsPrefix:{type:String,required:!0},rgba:{type:Array,default:null},alpha:{type:Number,default:0},onUpdateAlpha:{type:Function,required:!0},onComplete:Function},setup(e){const t=w(null);function i(a){!t.value||!e.rgba||(re("mousemove",document,n),re("mouseup",document,o),n(a))}function n(a){const{value:s}=t;if(!s)return;const{width:u,left:f}=s.getBoundingClientRect(),T=(a.clientX-f)/(u-At);e.onUpdateAlpha($t(T))}function o(){var a;ne("mousemove",document,n),ne("mouseup",document,o),(a=e.onComplete)===null||a===void 0||a.call(e)}return{railRef:t,railBackgroundImage:$(()=>{const{rgba:a}=e;return a?`linear-gradient(to right, rgba(${a[0]}, ${a[1]}, ${a[2]}, 0) 0%, rgba(${a[0]}, ${a[1]}, ${a[2]}, 1) 100%)`:""}),handleMouseDown:i}},render(){const{clsPrefix:e}=this;return l("div",{class:`${e}-color-picker-slider`,ref:"railRef",style:{height:le,borderRadius:O},onMousedown:this.handleMouseDown},l("div",{style:{borderRadius:O,position:"absolute",left:0,right:0,top:0,bottom:0,overflow:"hidden"}},l("div",{class:`${e}-color-picker-checkboard`}),l("div",{class:`${e}-color-picker-slider__image`,style:{backgroundImage:this.railBackgroundImage}})),this.rgba&&l("div",{style:{position:"absolute",left:O,right:O,top:0,bottom:0}},l("div",{class:`${e}-color-picker-handle`,style:{left:`calc(${this.alpha*100}% - ${O})`,borderRadius:O,width:le,height:le}},l("div",{class:`${e}-color-picker-handle__fill`,style:{backgroundColor:z(this.rgba),borderRadius:O,width:le,height:le}}))))}}),Ve=nt("n-color-picker");function _t(e){return/^\d{1,3}\.?\d*$/.test(e.trim())?Math.max(0,Math.min(Number.parseInt(e),255)):!1}function zt(e){return/^\d{1,3}\.?\d*$/.test(e.trim())?Math.max(0,Math.min(Number.parseInt(e),360)):!1}function Dt(e){return/^\d{1,3}\.?\d*$/.test(e.trim())?Math.max(0,Math.min(Number.parseInt(e),100)):!1}function Pt(e){const t=e.trim();return/^#[0-9a-fA-F]+$/.test(t)?[4,5,7,9].includes(t.length):!1}function It(e){return/^\d{1,3}\.?\d*%$/.test(e.trim())?Math.max(0,Math.min(Number.parseInt(e)/100,100)):!1}const Mt={paddingSmall:"0 4px"},Me=D({name:"ColorInputUnit",props:{label:{type:String,required:!0},value:{type:[Number,String],default:null},showAlpha:Boolean,onUpdateValue:{type:Function,required:!0}},setup(e){const t=w(""),{themeRef:i}=He(Ve,null);Be(()=>{t.value=n()});function n(){const{value:s}=e;if(s===null)return"";const{label:u}=e;return u==="HEX"?s:u==="A"?`${Math.floor(s*100)}%`:String(Math.floor(s))}function o(s){t.value=s}function a(s){let u,f;switch(e.label){case"HEX":f=Pt(s),f&&e.onUpdateValue(s),t.value=n();break;case"H":u=zt(s),u===!1?t.value=n():e.onUpdateValue(u);break;case"S":case"L":case"V":u=Dt(s),u===!1?t.value=n():e.onUpdateValue(u);break;case"A":u=It(s),u===!1?t.value=n():e.onUpdateValue(u);break;case"R":case"G":case"B":u=_t(s),u===!1?t.value=n():e.onUpdateValue(u);break}}return{mergedTheme:i,inputValue:t,handleInputChange:a,handleInputUpdateValue:o}},render(){const{mergedTheme:e}=this;return l(at,{size:"small",placeholder:this.label,theme:e.peers.Input,themeOverrides:e.peerOverrides.Input,builtinThemeOverrides:Mt,value:this.inputValue,onUpdateValue:this.handleInputUpdateValue,onChange:this.handleInputChange,style:this.label==="A"?"flex-grow: 1.25;":""})}}),Ft=D({name:"ColorInput",props:{clsPrefix:{type:String,required:!0},mode:{type:String,required:!0},modes:{type:Array,required:!0},showAlpha:{type:Boolean,required:!0},value:{type:String,default:null},valueArr:{type:Array,default:null},onUpdateValue:{type:Function,required:!0},onUpdateMode:{type:Function,required:!0}},setup(e){return{handleUnitUpdateValue(t,i){const{showAlpha:n}=e;if(e.mode==="hex"){e.onUpdateValue((n?B:ie)(i));return}let o;switch(e.valueArr===null?o=[0,0,0,0]:o=Array.from(e.valueArr),e.mode){case"hsv":o[t]=i,e.onUpdateValue((n?Z:Re)(o));break;case"rgb":o[t]=i,e.onUpdateValue((n?z:$e)(o));break;case"hsl":o[t]=i,e.onUpdateValue((n?H:Ue)(o));break}}}},render(){const{clsPrefix:e,modes:t}=this;return l("div",{class:`${e}-color-picker-input`},l("div",{class:`${e}-color-picker-input__mode`,onClick:this.onUpdateMode,style:{cursor:t.length===1?"":"pointer"}},this.mode.toUpperCase()+(this.showAlpha?"A":"")),l(ot,null,{default:()=>{const{mode:i,valueArr:n,showAlpha:o}=this;if(i==="hex"){let a=null;try{a=n===null?null:(o?B:ie)(n)}catch(s){}return l(Me,{label:"HEX",showAlpha:o,value:a,onUpdateValue:s=>{this.handleUnitUpdateValue(0,s)}})}return(i+(o?"a":"")).split("").map((a,s)=>l(Me,{label:a.toUpperCase(),value:n===null?null:n[s],onUpdateValue:u=>{this.handleUnitUpdateValue(s,u)}}))}}))}});function Ht(e,t){if(t==="hsv"){const[i,n,o,a]=j(e);return z([...F(i,n,o),a])}return e}function Bt(e){const t=document.createElement("canvas").getContext("2d");return t?(t.fillStyle=e,t.fillStyle):"#000000"}const Tt=D({name:"ColorPickerSwatches",props:{clsPrefix:{type:String,required:!0},mode:{type:String,required:!0},swatches:{type:Array,required:!0},onUpdateColor:{type:Function,required:!0}},setup(e){const t=$(()=>e.swatches.map(a=>{const s=se(a);return{value:a,mode:s,legalValue:Ht(a,s)}}));function i(a){const{mode:s}=e;let{value:u,mode:f}=a;return f||(f="hex",/^[a-zA-Z]+$/.test(u)?u=Bt(u):(lt("color-picker",`color ${u} in swatches is invalid.`),u="#000000")),f===s?u:qe(u,s,f)}function n(a){e.onUpdateColor(i(a))}function o(a,s){a.key==="Enter"&&n(s)}return{parsedSwatchesRef:t,handleSwatchSelect:n,handleSwatchKeyDown:o}},render(){const{clsPrefix:e}=this;return l("div",{class:`${e}-color-picker-swatches`},this.parsedSwatchesRef.map(t=>l("div",{class:`${e}-color-picker-swatch`,tabindex:0,onClick:()=>{this.handleSwatchSelect(t)},onKeydown:i=>{this.handleSwatchKeyDown(i,t)}},l("div",{class:`${e}-color-picker-swatch__fill`,style:{background:t.legalValue}}))))}}),qt=D({name:"ColorPickerTrigger",slots:Object,props:{clsPrefix:{type:String,required:!0},value:{type:String,default:null},hsla:{type:Array,default:null},disabled:Boolean,onClick:Function},setup(e){const{colorPickerSlots:t,renderLabelRef:i}=He(Ve,null);return()=>{const{hsla:n,value:o,clsPrefix:a,onClick:s,disabled:u}=e,f=t.label||i.value;return l("div",{class:[`${a}-color-picker-trigger`,u&&`${a}-color-picker-trigger--disabled`],onClick:u?void 0:s},l("div",{class:`${a}-color-picker-trigger__fill`},l("div",{class:`${a}-color-picker-checkboard`}),l("div",{style:{position:"absolute",left:0,right:0,top:0,bottom:0,backgroundColor:n?H(n):""}}),o&&n?l("div",{class:`${a}-color-picker-trigger__value`,style:{color:n[2]>50||n[3]<.5?"black":"white"}},f?f(o):o):null))}}}),Et=D({name:"ColorPreview",props:{clsPrefix:{type:String,required:!0},mode:{type:String,required:!0},color:{type:String,default:null,validator:e=>{const t=se(e);return!!(!e||t&&t!=="hsv")}},onUpdateColor:{type:Function,required:!0}},setup(e){function t(i){var n;const o=i.target.value;(n=e.onUpdateColor)===null||n===void 0||n.call(e,qe(o.toUpperCase(),e.mode,"hex")),i.stopPropagation()}return{handleChange:t}},render(){const{clsPrefix:e}=this;return l("div",{class:`${e}-color-picker-preview__preview`},l("span",{class:`${e}-color-picker-preview__fill`,style:{background:this.color||"#000000"}}),l("input",{class:`${e}-color-picker-preview__input`,type:"color",value:this.color,onChange:this.handleChange}))}}),ee="12px",Nt=12,L="6px",Ot=6,Lt="linear-gradient(90deg,red,#ff0 16.66%,#0f0 33.33%,#0ff 50%,#00f 66.66%,#f0f 83.33%,red)",jt=D({name:"HueSlider",props:{clsPrefix:{type:String,required:!0},hue:{type:Number,required:!0},onUpdateHue:{type:Function,required:!0},onComplete:Function},setup(e){const t=w(null);function i(a){t.value&&(re("mousemove",document,n),re("mouseup",document,o),n(a))}function n(a){const{value:s}=t;if(!s)return;const{width:u,left:f}=s.getBoundingClientRect(),T=Ut((a.clientX-f-Ot)/(u-Nt)*360);e.onUpdateHue(T)}function o(){var a;ne("mousemove",document,n),ne("mouseup",document,o),(a=e.onComplete)===null||a===void 0||a.call(e)}return{railRef:t,handleMouseDown:i}},render(){const{clsPrefix:e}=this;return l("div",{class:`${e}-color-picker-slider`,style:{height:ee,borderRadius:L}},l("div",{ref:"railRef",style:{boxShadow:"inset 0 0 2px 0 rgba(0, 0, 0, .24)",boxSizing:"border-box",backgroundImage:Lt,height:ee,borderRadius:L,position:"relative"},onMousedown:this.handleMouseDown},l("div",{style:{position:"absolute",left:L,right:L,top:0,bottom:0}},l("div",{class:`${e}-color-picker-handle`,style:{left:`calc((${this.hue}%) / 359 * 100 - ${L})`,borderRadius:L,width:ee,height:ee}},l("div",{class:`${e}-color-picker-handle__fill`,style:{backgroundColor:`hsl(${this.hue}, 100%, 50%)`,borderRadius:L,width:ee,height:ee}})))))}}),pe="12px",fe="6px",Zt=D({name:"Pallete",props:{clsPrefix:{type:String,required:!0},rgba:{type:Array,default:null},displayedHue:{type:Number,required:!0},displayedSv:{type:Array,required:!0},onUpdateSV:{type:Function,required:!0},onComplete:Function},setup(e){const t=w(null);function i(a){t.value&&(re("mousemove",document,n),re("mouseup",document,o),n(a))}function n(a){const{value:s}=t;if(!s)return;const{width:u,height:f,left:T,bottom:ae}=s.getBoundingClientRect(),q=(ae-a.clientY)/f,K=(a.clientX-T)/u,ue=100*(K>1?1:K<0?0:K),X=100*(q>1?1:q<0?0:q);e.onUpdateSV(ue,X)}function o(){var a;ne("mousemove",document,n),ne("mouseup",document,o),(a=e.onComplete)===null||a===void 0||a.call(e)}return{palleteRef:t,handleColor:$(()=>{const{rgba:a}=e;return a?`rgb(${a[0]}, ${a[1]}, ${a[2]})`:""}),handleMouseDown:i}},render(){const{clsPrefix:e}=this;return l("div",{class:`${e}-color-picker-pallete`,onMousedown:this.handleMouseDown,ref:"palleteRef"},l("div",{class:`${e}-color-picker-pallete__layer`,style:{backgroundImage:`linear-gradient(90deg, white, hsl(${this.displayedHue}, 100%, 50%))`}}),l("div",{class:`${e}-color-picker-pallete__layer ${e}-color-picker-pallete__layer--shadowed`,style:{backgroundImage:"linear-gradient(180deg, rgba(0, 0, 0, 0%), rgba(0, 0, 0, 100%))"}}),this.rgba&&l("div",{class:`${e}-color-picker-handle`,style:{width:pe,height:pe,borderRadius:fe,left:`calc(${this.displayedSv[0]}% - ${fe})`,bottom:`calc(${this.displayedSv[1]}% - ${fe})`}},l("div",{class:`${e}-color-picker-handle__fill`,style:{backgroundColor:this.handleColor,borderRadius:fe,width:pe,height:pe}})))}}),Kt=Q([b("color-picker",`
 display: inline-block;
 box-sizing: border-box;
 height: var(--n-height);
 font-size: var(--n-font-size);
 width: 100%;
 position: relative;
 `),b("color-picker-panel",`
 margin: 4px 0;
 width: 240px;
 font-size: var(--n-panel-font-size);
 color: var(--n-text-color);
 background-color: var(--n-color);
 transition:
 box-shadow .3s var(--n-bezier),
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 border-radius: var(--n-border-radius);
 box-shadow: var(--n-box-shadow);
 `,[it(),b("input",`
 text-align: center;
 `)]),b("color-picker-checkboard",`
 background: white; 
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `,[Q("&::after",`
 background-image: linear-gradient(45deg, #DDD 25%, #0000 25%), linear-gradient(-45deg, #DDD 25%, #0000 25%), linear-gradient(45deg, #0000 75%, #DDD 75%), linear-gradient(-45deg, #0000 75%, #DDD 75%);
 background-size: 12px 12px;
 background-position: 0 0, 0 6px, 6px -6px, -6px 0px;
 background-repeat: repeat;
 content: "";
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),b("color-picker-slider",`
 margin-bottom: 8px;
 position: relative;
 box-sizing: border-box;
 `,[U("image",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `),Q("&::after",`
 content: "";
 position: absolute;
 border-radius: inherit;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 box-shadow: inset 0 0 2px 0 rgba(0, 0, 0, .24);
 pointer-events: none;
 `)]),b("color-picker-handle",`
 z-index: 1;
 box-shadow: 0 0 2px 0 rgba(0, 0, 0, .45);
 position: absolute;
 background-color: white;
 overflow: hidden;
 `,[U("fill",`
 box-sizing: border-box;
 border: 2px solid white;
 `)]),b("color-picker-pallete",`
 height: 180px;
 position: relative;
 margin-bottom: 8px;
 cursor: crosshair;
 `,[U("layer",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `,[De("shadowed",`
 box-shadow: inset 0 0 2px 0 rgba(0, 0, 0, .24);
 `)])]),b("color-picker-preview",`
 display: flex;
 `,[U("sliders",`
 flex: 1 0 auto;
 `),U("preview",`
 position: relative;
 height: 30px;
 width: 30px;
 margin: 0 0 8px 6px;
 border-radius: 50%;
 box-shadow: rgba(0, 0, 0, .15) 0px 0px 0px 1px inset;
 overflow: hidden;
 `),U("fill",`
 display: block;
 width: 30px;
 height: 30px;
 `),U("input",`
 position: absolute;
 top: 0;
 left: 0;
 width: 30px;
 height: 30px;
 opacity: 0;
 z-index: 1;
 `)]),b("color-picker-input",`
 display: flex;
 align-items: center;
 `,[b("input",`
 flex-grow: 1;
 flex-basis: 0;
 `),U("mode",`
 width: 72px;
 text-align: center;
 `)]),b("color-picker-control",`
 padding: 12px;
 `),b("color-picker-action",`
 display: flex;
 margin-top: -4px;
 border-top: 1px solid var(--n-divider-color);
 padding: 8px 12px;
 justify-content: flex-end;
 `,[b("button","margin-left: 8px;")]),b("color-picker-trigger",`
 border: var(--n-border);
 height: 100%;
 box-sizing: border-box;
 border-radius: var(--n-border-radius);
 transition: border-color .3s var(--n-bezier);
 cursor: pointer;
 `,[U("value",`
 white-space: nowrap;
 position: relative;
 `),U("fill",`
 border-radius: var(--n-border-radius);
 position: absolute;
 display: flex;
 align-items: center;
 justify-content: center;
 left: 4px;
 right: 4px;
 top: 4px;
 bottom: 4px;
 `),De("disabled","cursor: not-allowed"),b("color-picker-checkboard",`
 border-radius: var(--n-border-radius);
 `,[Q("&::after",`
 --n-block-size: calc((var(--n-height) - 8px) / 3);
 background-size: calc(var(--n-block-size) * 2) calc(var(--n-block-size) * 2);
 background-position: 0 0, 0 var(--n-block-size), var(--n-block-size) calc(-1 * var(--n-block-size)), calc(-1 * var(--n-block-size)) 0px; 
 `)])]),b("color-picker-swatches",`
 display: grid;
 grid-gap: 8px;
 flex-wrap: wrap;
 position: relative;
 grid-template-columns: repeat(auto-fill, 18px);
 margin-top: 10px;
 `,[b("color-picker-swatch",`
 width: 18px;
 height: 18px;
 background-image: linear-gradient(45deg, #DDD 25%, #0000 25%), linear-gradient(-45deg, #DDD 25%, #0000 25%), linear-gradient(45deg, #0000 75%, #DDD 75%), linear-gradient(-45deg, #0000 75%, #DDD 75%);
 background-size: 8px 8px;
 background-position: 0px 0, 0px 4px, 4px -4px, -4px 0px;
 background-repeat: repeat;
 `,[U("fill",`
 position: relative;
 width: 100%;
 height: 100%;
 border-radius: 3px;
 box-shadow: rgba(0, 0, 0, .15) 0px 0px 0px 1px inset;
 cursor: pointer;
 `),Q("&:focus",`
 outline: none;
 `,[U("fill",[Q("&::after",`
 position: absolute;
 top: 0;
 right: 0;
 bottom: 0;
 left: 0;
 background: inherit;
 filter: blur(2px);
 content: "";
 `)])])])])]),Xt=Object.assign(Object.assign({},Te.props),{value:String,show:{type:Boolean,default:void 0},defaultShow:Boolean,defaultValue:String,modes:{type:Array,default:()=>["rgb","hex","hsl"]},placement:{type:String,default:"bottom-start"},to:Ae.propTo,showAlpha:{type:Boolean,default:!0},showPreview:Boolean,swatches:Array,disabled:{type:Boolean,default:void 0},actions:{type:Array,default:null},internalActions:Array,size:String,renderLabel:Function,onComplete:Function,onConfirm:Function,onClear:Function,"onUpdate:show":[Function,Array],onUpdateShow:[Function,Array],"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array]}),Wt=D({name:"ColorPicker",props:Xt,slots:Object,setup(e,{slots:t}){const i=w(null);let n=null;const o=ft(e),{mergedSizeRef:a,mergedDisabledRef:s}=o,{localeRef:u}=gt("global"),{mergedClsPrefixRef:f,namespaceRef:T,inlineThemeDisabled:ae}=vt(e),q=Te("ColorPicker","-color-picker",Kt,bt,e,f);mt(Ve,{themeRef:q,renderLabelRef:we(e,"renderLabel"),colorPickerSlots:t});const K=w(e.defaultShow),ue=Pe(we(e,"show"),K);function X(r){const{onUpdateShow:c,"onUpdate:show":h}=e;c&&de(c,r),h&&de(h,r),K.value=r}const{defaultValue:_e}=e,ze=w(_e===void 0?Ct(e.modes,e.showAlpha):_e),x=Pe(we(e,"value"),ze),G=w([x.value]),A=w(0),ve=$(()=>se(x.value)),{modes:Ee}=e,R=w(se(x.value)||Ee[0]||"rgb");function Ne(){const{modes:r}=e,{value:c}=R,h=r.findIndex(p=>p===c);~h?R.value=r[(h+1)%r.length]:R.value="rgb"}let y,S,W,Y,P,I,M,C;const oe=$(()=>{const{value:r}=x;if(!r)return null;switch(ve.value){case"hsv":return j(r);case"hsl":return[y,S,W,C]=te(r),[...Fe(y,S,W),C];case"rgb":case"hex":return[P,I,M,C]=_(r),[...Se(P,I,M),C]}}),E=$(()=>{const{value:r}=x;if(!r)return null;switch(ve.value){case"rgb":case"hex":return _(r);case"hsv":return[y,S,Y,C]=j(r),[...F(y,S,Y),C];case"hsl":return[y,S,W,C]=te(r),[...ye(y,S,W),C]}}),be=$(()=>{const{value:r}=x;if(!r)return null;switch(ve.value){case"hsl":return te(r);case"hsv":return[y,S,Y,C]=j(r),[...ge(y,S,Y),C];case"rgb":case"hex":return[P,I,M,C]=_(r),[...Ce(P,I,M),C]}}),Oe=$(()=>{switch(R.value){case"rgb":case"hex":return E.value;case"hsv":return oe.value;case"hsl":return be.value}}),ce=w(0),me=w(1),xe=w([0,0]);function Le(r,c){const{value:h}=oe,p=ce.value,g=h?h[3]:1;xe.value=[r,c];const{showAlpha:d}=e;switch(R.value){case"hsv":v((d?Z:Re)([p,r,c,g]),"cursor");break;case"hsl":v((d?H:Ue)([...ge(p,r,c),g]),"cursor");break;case"rgb":v((d?z:$e)([...F(p,r,c),g]),"cursor");break;case"hex":v((d?B:ie)([...F(p,r,c),g]),"cursor");break}}function je(r){ce.value=r;const{value:c}=oe;if(!c)return;const[,h,p,g]=c,{showAlpha:d}=e;switch(R.value){case"hsv":v((d?Z:Re)([r,h,p,g]),"cursor");break;case"rgb":v((d?z:$e)([...F(r,h,p),g]),"cursor");break;case"hex":v((d?B:ie)([...F(r,h,p),g]),"cursor");break;case"hsl":v((d?H:Ue)([...ge(r,h,p),g]),"cursor");break}}function Ze(r){switch(R.value){case"hsv":[y,S,Y]=oe.value,v(Z([y,S,Y,r]),"cursor");break;case"rgb":[P,I,M]=E.value,v(z([P,I,M,r]),"cursor");break;case"hex":[P,I,M]=E.value,v(B([P,I,M,r]),"cursor");break;case"hsl":[y,S,W]=be.value,v(H([y,S,W,r]),"cursor");break}me.value=r}function v(r,c){c==="cursor"?n=r:n=null;const{nTriggerFormChange:h,nTriggerFormInput:p}=o,{onUpdateValue:g,"onUpdate:value":d}=e;g&&de(g,r),d&&de(d,r),h(),p(),ze.value=r}function Ke(r){v(r,"input"),St(J)}function J(r=!0){const{value:c}=x;if(c){const{nTriggerFormChange:h,nTriggerFormInput:p}=o,{onComplete:g}=e;g&&g(c);const{value:d}=G,{value:k}=A;r&&(d.splice(k+1,d.length,c),A.value=k+1),h(),p()}}function Xe(){const{value:r}=A;r-1<0||(v(G.value[r-1],"input"),J(!1),A.value=r-1)}function Ge(){const{value:r}=A;r<0||r+1>=G.value.length||(v(G.value[r+1],"input"),J(!1),A.value=r+1)}function We(){v(null,"input");const{onClear:r}=e;r&&r(),X(!1)}function Ye(){const{value:r}=x,{onConfirm:c}=e;c&&c(r),X(!1)}const Je=$(()=>A.value>=1),Qe=$(()=>{const{value:r}=G;return r.length>1&&A.value<r.length-1});xt(ue,r=>{r||(G.value=[x.value],A.value=0)}),Be(()=>{if(!(n&&n===x.value)){const{value:r}=oe;r&&(ce.value=r[0],me.value=r[3],xe.value=[r[1],r[2]])}n=null});const ke=$(()=>{const{value:r}=a,{common:{cubicBezierEaseInOut:c},self:{textColor:h,color:p,panelFontSize:g,boxShadow:d,border:k,borderRadius:m,dividerColor:N,[Ie("height",r)]:tt,[Ie("fontSize",r)]:rt}}=q.value;return{"--n-bezier":c,"--n-text-color":h,"--n-color":p,"--n-panel-font-size":g,"--n-font-size":rt,"--n-box-shadow":d,"--n-border":k,"--n-border-radius":m,"--n-height":tt,"--n-divider-color":N}}),V=ae?kt("color-picker",$(()=>a.value[0]),ke,e):void 0;function et(){var r;const{value:c}=E,{value:h}=ce,{internalActions:p,modes:g,actions:d}=e,{value:k}=q,{value:m}=f;return l("div",{class:[`${m}-color-picker-panel`,V==null?void 0:V.themeClass.value],onDragstart:N=>{N.preventDefault()},style:ae?void 0:ke.value},l("div",{class:`${m}-color-picker-control`},l(Zt,{clsPrefix:m,rgba:c,displayedHue:h,displayedSv:xe.value,onUpdateSV:Le,onComplete:J}),l("div",{class:`${m}-color-picker-preview`},l("div",{class:`${m}-color-picker-preview__sliders`},l(jt,{clsPrefix:m,hue:h,onUpdateHue:je,onComplete:J}),e.showAlpha?l(Vt,{clsPrefix:m,rgba:c,alpha:me.value,onUpdateAlpha:Ze,onComplete:J}):null),e.showPreview?l(Et,{clsPrefix:m,mode:R.value,color:E.value&&ie(E.value),onUpdateColor:N=>{v(N,"input")}}):null),l(Ft,{clsPrefix:m,showAlpha:e.showAlpha,mode:R.value,modes:g,onUpdateMode:Ne,value:x.value,valueArr:Oe.value,onUpdateValue:Ke}),((r=e.swatches)===null||r===void 0?void 0:r.length)&&l(Tt,{clsPrefix:m,mode:R.value,swatches:e.swatches,onUpdateColor:N=>{v(N,"input")}})),d!=null&&d.length?l("div",{class:`${m}-color-picker-action`},d.includes("confirm")&&l(he,{size:"small",onClick:Ye,theme:k.peers.Button,themeOverrides:k.peerOverrides.Button},{default:()=>u.value.confirm}),d.includes("clear")&&l(he,{size:"small",onClick:We,disabled:!x.value,theme:k.peers.Button,themeOverrides:k.peerOverrides.Button},{default:()=>u.value.clear})):null,t.action?l("div",{class:`${m}-color-picker-action`},{default:t.action}):p?l("div",{class:`${m}-color-picker-action`},p.includes("undo")&&l(he,{size:"small",onClick:Xe,disabled:!Je.value,theme:k.peers.Button,themeOverrides:k.peerOverrides.Button},{default:()=>u.value.undo}),p.includes("redo")&&l(he,{size:"small",onClick:Ge,disabled:!Qe.value,theme:k.peers.Button,themeOverrides:k.peerOverrides.Button},{default:()=>u.value.redo})):null)}return{mergedClsPrefix:f,namespace:T,selfRef:i,hsla:be,rgba:E,mergedShow:ue,mergedDisabled:s,isMounted:wt(),adjustedTo:Ae(e),mergedValue:x,handleTriggerClick(){X(!0)},handleClickOutside(r){var c;!((c=i.value)===null||c===void 0)&&c.contains(yt(r))||X(!1)},renderPanel:et,cssVars:ae?void 0:ke,themeClass:V==null?void 0:V.themeClass,onRender:V==null?void 0:V.onRender}},render(){const{mergedClsPrefix:e,onRender:t}=this;return t==null||t(),l("div",{class:[this.themeClass,`${e}-color-picker`],ref:"selfRef",style:this.cssVars},l(st,null,{default:()=>[l(ut,null,{default:()=>l(qt,{clsPrefix:e,value:this.mergedValue,hsla:this.hsla,disabled:this.mergedDisabled,onClick:this.handleTriggerClick})}),l(ct,{placement:this.placement,show:this.mergedShow,containerClass:this.namespace,teleportDisabled:this.adjustedTo===Ae.tdkey,to:this.adjustedTo},{default:()=>l(dt,{name:"fade-in-scale-up-transition",appear:this.isMounted},{default:()=>this.mergedShow?ht(this.renderPanel(),[[pt,this.handleClickOutside,void 0,{capture:!0}]]):null})})]}))}});export{Wt as _};
