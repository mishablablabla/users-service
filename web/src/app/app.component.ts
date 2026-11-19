import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { User, UserService } from './user.service';

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit {
  private api = inject(UserService);

  users: User[] = [];
  form = { name: '', email: '' };
  editingId: number | null = null;
  error = '';

  ngOnInit() {
    this.load();
  }

  load() {
    this.api.list().subscribe({
      next: (u) => (this.users = u),
      error: (e) => this.fail(e)
    });
  }

  save() {
    this.error = '';
    const done = () => {
      this.reset();
      this.load();
    };
    const req =
      this.editingId === null
        ? this.api.create(this.form)
        : this.api.update(this.editingId, this.form);
    req.subscribe({ next: done, error: (e) => this.fail(e) });
  }

  edit(u: User) {
    this.editingId = u.id;
    this.form = { name: u.name, email: u.email };
  }

  remove(u: User) {
    this.api.remove(u.id).subscribe({ next: () => this.load(), error: (e) => this.fail(e) });
  }

  reset() {
    this.editingId = null;
    this.form = { name: '', email: '' };
  }

  private fail(e: HttpErrorResponse) {
    this.error = e.error?.detail
      ? typeof e.error.detail === 'string'
        ? e.error.detail
        : 'Invalid input'
      : `Request failed (${e.status})`;
  }
}
