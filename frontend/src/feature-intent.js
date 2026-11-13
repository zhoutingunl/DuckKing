// Audio permission/downloads may finish after Stop or a scene switch.
export function createFeatureIntent(){
 let version=0;
 return {
  cancel(){version++},
  async run(prepare,execute){
   const mine=++version;
   try{await prepare()}catch(error){if(mine!==version)return false;throw error}
   if(mine!==version)return false;
   await execute();return true;
  },
 };
}
