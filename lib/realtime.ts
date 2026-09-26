import { io, type Socket } from 'socket.io-client'
import { supabase } from './supabase-client'

/** One socket for the tab, shared by whatever is on screen.
 *
 *  The server puts a client in the room of every notebook it belongs to, so
 *  connecting once is enough: a component subscribes to the events it cares
 *  about and filters by notebook. Reconnection, backoff and the transport
 *  upgrade are socket.io-client's job, not ours. */
let socket: Socket | null = null

const URL = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api').replace(/\/api\/?$/, '')

export async function getSocket(): Promise<Socket | null> {
  if (!supabase) return null
  if (socket) return socket
  const token = (await supabase.auth.getSession()).data.session?.access_token
  if (!token) return null

  socket = io(URL, {
    // The token travels in the handshake, where the server checks it before
    // admitting the client to any room.
    auth: { token },
    transports: ['websocket', 'polling'],
    reconnectionDelay: 500,
    reconnectionDelayMax: 5000,
  })
  return socket
}

/** Drops the connection, e.g. on sign-out, so the next session authenticates
 *  with its own token rather than inheriting this one. */
export function closeSocket() {
  socket?.close()
  socket = null
}
