import { createBrowserRouter } from "react-router"

import { requireAuth } from "@/lib/require-auth"

export const router = createBrowserRouter([
  {
    path: "/",
    lazy: () => import("@/routes/root"),
    children: [
      {
        path: "login",
        lazy: () => import("@/routes/login"),
      },
      {
        path: "signup",
        lazy: () => import("@/routes/signup"),
      },
      {
        path: "signup/complete",
        lazy: () => import("@/routes/signup-complete"),
      },
      {
        path: "join/:code?",
        lazy: () => import("@/routes/join"),
      },
      {
        middleware: [requireAuth],
        children: [
          {
            index: true,
            lazy: () => import("@/routes/home"),
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
            path: "reauthenticate",
            lazy: () => import("@/routes/reauthenticate"),
          },
        ],
      },
      {
        path: "*",
        lazy: () => import("@/routes/not-found"),
      },
    ],
  },
])
