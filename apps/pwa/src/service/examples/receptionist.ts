import type { StudentService } from "../studentService";

export const receptionistService: StudentService = {
  title: "Mobile receptionist",
  async run(service) {
    service.say("Welcome. Where would you like to go?");
    const destination = await service.choose("Destination?", ["Entrance", "Desk"]);
    await service.confirm("Ready to follow me?", "Let's go");
    await service.guideTo(destination === "Desk" ? "desk" : "entrance");
    service.say(`We have arrived at the ${destination.toLowerCase()}.`);
  }
};
