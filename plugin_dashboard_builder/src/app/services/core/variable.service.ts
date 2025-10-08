import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { client, WorkbookVariable } from '@sigmacomputing/plugin';

@Injectable({
    providedIn: 'root'
})
export class VariableService {
    
    // store multiple variable subjects for different variable IDs
    private variableSubjects: { [key: string]: BehaviorSubject<WorkbookVariable | undefined> } = {};

    getVariable(id: string): Observable<WorkbookVariable | undefined> {
        if (!id) {
            return new BehaviorSubject<WorkbookVariable | undefined>(undefined).asObservable();
        }

        if (!this.variableSubjects[id]) {
            // initialize with current value
            const currentValue = client.config.getVariable(id);
            this.variableSubjects[id] = new BehaviorSubject<WorkbookVariable | undefined>(currentValue);
            
            // subscribe to changes
            client.config.subscribeToWorkbookVariable(id, (variable: WorkbookVariable) => {
                this.variableSubjects[id].next(variable);
            });
        }

        return this.variableSubjects[id].asObservable();
    }

    setVariable(id: string, ...values: unknown[]): void {
        if (id) {
            client.config.setVariable(id, ...values);
        }
    }

    // helper method to get current value synchronously
    getVariableValue(id: string): WorkbookVariable | undefined {
        if (!id) {
            return undefined;
        }
        return client.config.getVariable(id);
    }
} 