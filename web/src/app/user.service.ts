import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface User {
  id: number;
  name: string;
  email: string;
}
export type UserInput = Omit<User, 'id'>;

// Relative URL: in Kubernetes the Ingress routes /api to the backend,
// locally `ng serve` proxies it (proxy.conf.json) and nginx proxies it in the container.
const BASE = '/api/users';

@Injectable({ providedIn: 'root' })
export class UserService {
  private http = inject(HttpClient);

  list(): Observable<User[]> {
    return this.http.get<User[]>(BASE);
  }
  create(u: UserInput): Observable<User> {
    return this.http.post<User>(BASE, u);
  }
  update(id: number, u: UserInput): Observable<User> {
    return this.http.put<User>(`${BASE}/${id}`, u);
  }
  remove(id: number): Observable<void> {
    return this.http.delete<void>(`${BASE}/${id}`);
  }
}
