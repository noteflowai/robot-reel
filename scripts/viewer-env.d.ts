// Check-time environment for the inline viewer scripts. Not shipped, not loaded
// by any page: it only tells the TypeScript compiler what the templates assume.
//
// The templates look elements up with a `$` helper over getElementById and then
// use them as the concrete element they are (`video.currentTime`, `range.value`).
// Widening the lookups keeps the check focused on defects that are real for this
// code — undeclared names, typos, wrong arity, dead locals, unreachable branches
// — instead of demanding a cast at every element access. Tighten these when a
// template starts declaring its elements explicitly.

interface Document {
  getElementById(elementId: string): any;
  querySelector(selectors: string): any;
  querySelectorAll(selectors: string): any;
  // Keyboard shortcuts read event.target.tagName to skip form controls.
  addEventListener(type: string, listener: (event: any) => any, options?: any): void;
}

// These pinned import-map dependencies are exercised by the actual 3D browser
// checks. Ambient module names let checkJs analyze our orchestration separately.
declare module "three";
declare module "three/addons/*";
declare module "@sparkjsdev/spark";
