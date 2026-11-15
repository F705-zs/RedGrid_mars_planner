import { useMission } from "@/api/queries";
import { useRegionById } from "@/lib/region-context";

/** Shared loader state for /missions/$id/* screens. */
export function useMissionPage(idParam: string) {
  const id = Number(idParam);
  const valid = Number.isInteger(id) && id > 0;
  const mission = useMission(valid ? id : -1);
  const region = useRegionById(mission.data?.regionId);
  return { id, valid, mission, region, finalized: mission.data?.status === "FINALIZED" };
}
