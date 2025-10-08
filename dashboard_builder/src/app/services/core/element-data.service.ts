import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { client, WorkbookElementData } from '@sigmacomputing/plugin';

@Injectable({
    providedIn: 'root'
})
export class ElementDataService {
    
    // store multiple element data subjects for different config IDs
    private elementDataSubjects: { [key: string]: BehaviorSubject<WorkbookElementData> } = {};

    getElementData(configId: string): Observable<WorkbookElementData> {
        if (!configId) {
            return new BehaviorSubject<WorkbookElementData>({}).asObservable();
        }

        if (!this.elementDataSubjects[configId]) {
            this.elementDataSubjects[configId] = new BehaviorSubject<WorkbookElementData>({});
            client.elements.subscribeToElementData(configId, (data: WorkbookElementData) => {
                this.elementDataSubjects[configId].next(data);
            });
        }

        return this.elementDataSubjects[configId].asObservable();
    }
}