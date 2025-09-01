import React from "react";

interface Task {
  id: string;
  phase: string;
  description: string;
}

interface Props {
  tasks: Task[];
  paused: boolean;
}

const PhaseCascade: React.FC<Props> = ({ tasks }) => (
  <div className="phase-cascade h-full">
    {/* TODO: Implementierung der Phasen-Graphik mit React-Flow oder SVG */}
    {tasks.map((task) => (
      <div key={task.id} className="phase-node">
        <span className="font-semibold">{task.phase}</span>
        <span>{task.description}</span>
      </div>
    ))}
  </div>
);

export default PhaseCascade;

