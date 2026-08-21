import { createBrowserRouter } from "react-router"

export const router = createBrowserRouter([
  {
    path: "/",
    lazy: () => import("@/routes/root"),

    children: [
      {
        index: true,
        lazy: () => import("@/routes/home"),
      },
      {
        path: "login",
        lazy: () => import("@/routes/login"),
      },
      {
        path: "join/:code?",
        lazy: () => import("@/routes/join"),
      },

      {
        path: "classrooms",

        children: [
          {
            index: true,
            lazy: () => import("@/routes/classrooms"),
          },
          {
            path: ":classroomId",

            children: [
              {
                index: true,
                lazy: () => import("@/routes/classroom/overview"),
              },
              {
                path: "students",
                lazy: () => import("@/routes/classroom/students"),
              },
              {
                path: "students/:studentId",
                lazy: () => import("@/routes/classroom/student"),
              },
              {
                path: "assignments",
                lazy: () => import("@/routes/classroom/assignments"),
              },
              {
                path: "assignments/:assignmentId",
                lazy: () => import("@/routes/classroom/assignment"),
              },
              {
                path: "sessions",
                lazy: () => import("@/routes/classroom/sessions"),
              },
              {
                path: "sessions/:sessionId",
                lazy: () => import("@/routes/classroom/session"),
              },
              {
                path: "analytics",
                lazy: () => import("@/routes/classroom/analytics"),
              },
              {
                path: "settings",
                lazy: () => import("@/routes/classroom/settings"),
              },
            ],
          },
        ],
      },

      {
        path: "settings",
        lazy: () => import("@/routes/settings"),
      },
      {
        path: "*",
        lazy: () => import("@/routes/not-found"),
      },
    ],
  },
])
