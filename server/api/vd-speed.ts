import { XMLParser } from "fast-xml-parser";

export default cachedEventHandler(
  async (event) => {
    // TODO: add caching layer to avoid fetching and parsing XML on every request
    const response = await fetch("https://tisvcloud.freeway.gov.tw/history/motc20/VDLive.xml");
    const xmlString = await response.text();

    const parser = new XMLParser({
      ignoreAttributes: true,
      isArray: (name: string) => ["VDLive", "LinkFlow", "Lane", "Vehicle"].includes(name),
    });

    const parsedObj = parser.parse(xmlString);
    const vdLives = parsedObj?.VDLiveList?.VDLives?.VDLive || [];

    const linkSpeeds: Record<string, { avg: number; lanes: Record<string, number> }> = {};

    for (const vd of vdLives) {
      const linkFlows = vd.LinkFlows?.LinkFlow || [];
      for (const flow of linkFlows) {
        const linkId = flow.LinkID;
        const lanes = flow.Lanes?.Lane || [];

        const laneData: Record<string, number> = {};
        let totalSpeed = 0;
        let validCount = 0;

        for (const lane of lanes) {
          const laneId = String(lane.LaneID);
          const speed = Number(lane.Speed) || 0;
          if (speed > 0) {
            laneData[laneId] = speed;
            totalSpeed += speed;
            validCount += 1;
          }
        }

        if (validCount > 0) {
          linkSpeeds[linkId] = {
            avg: Math.round(totalSpeed / validCount),
            lanes: laneData,
          };
        }
      }
    }

    return linkSpeeds;
  },
  {
    maxAge: 60, // cache for 60 seconds
    getKey: () => "vd-speed",
  },
);
