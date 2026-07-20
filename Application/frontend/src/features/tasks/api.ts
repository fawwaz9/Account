import { get } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { Task } from "./types";

export async function fetchTasks(userId: string): Promise<Task[]> {
  return get<Task[]>(endpoints.tasks.list(userId));
}
