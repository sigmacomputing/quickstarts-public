import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { client } from '@sigmacomputing/plugin';

@Injectable({
    providedIn: 'root',
})
export class ConfigService {

    private configSubject = new BehaviorSubject<any>(client.config.get());

    constructor() {
        client.config.subscribe((newConfig: any) => {
            this.configSubject.next(newConfig);
        });
    }

    getConfig(): Observable<any> {
        return this.configSubject.asObservable();
    }

    getConfigKey(key: string): Observable<any> {
        return new Observable((observer) => {
            const subscription = this.configSubject.subscribe((config) => {
                observer.next(config[key]);
            });
            return () => subscription.unsubscribe();
        });
    }
    
}