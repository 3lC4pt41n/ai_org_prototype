import React from "react";
import usePipelineStore from "../store/pipelineStore";

export default function BacklogList() {
  const { backlog } = usePipelineStore();
  return (
    <div className="border rounded p-2">
      <h2 className="font-semibold mb-2">Backlog</h2>
      {backlog.length === 0 ? (
        <p className="text-gray-500">Kein Backlog.</p>
      ) : (
        <ul className="space-y-1">
          {backlog.map((task) => (
            <li key={task.id}>
              {task.name} - <span className="capitalize">{task.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
