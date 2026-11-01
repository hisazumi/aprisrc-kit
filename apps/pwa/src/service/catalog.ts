import type { ServiceMode } from "../navigation";
import type { StudentService } from "./studentService";
import { studentCarry } from "../missions/studentCarry";
import studentSource from "../missions/studentCarry.ts?raw";
import { carryService } from "./examples/carry";
import carrySource from "./examples/carry.ts?raw";
import { greetingService } from "./examples/greeting";
import greetingSource from "./examples/greeting.ts?raw";
import { receptionistService } from "./examples/receptionist";
import receptionistSource from "./examples/receptionist.ts?raw";

export const serviceCatalog: Record<ServiceMode, {
  definition: StudentService; source: string; file: string; markers?: boolean;
}> = {
  student: { definition: studentCarry, source: studentSource, file: "missions/studentCarry.ts" },
  carry: { definition: carryService, source: carrySource, file: "service/examples/carry.ts" },
  greeting: { definition: greetingService, source: greetingSource, file: "service/examples/greeting.ts" },
  receptionist: { definition: receptionistService, source: receptionistSource,
    file: "service/examples/receptionist.ts", markers: true }
};
